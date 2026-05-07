"""
backend/app/services/llm_client.py
────────────────────────────────────
Thin async wrapper around the Ollama Python SDK.

Responsibilities:
  - Code completion  (fill-in-the-middle style prompt)
  - Code explanation (instruction-following prompt)
  - Chat             (multi-turn conversation)
  - Streaming        (yields token chunks for the chat panel SSE endpoint)
  - Retry logic      (tenacity: 3 attempts, exponential back-off)
  - Token estimation (tiktoken: keeps prompts inside the context window)

All prompt templates live here so route handlers stay clean.
"""

import asyncio
from typing import AsyncGenerator, List, Optional

import ollama as ollama_sdk
import tiktoken
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.models.schemas import ChatMessage, ChatRole, SupportedLanguage


# tiktoken doesn't have a codellama/deepseek tokenizer, so we use the closest
# OpenAI equivalent for *counting* purposes only (not for actual tokenisation).
_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text))


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Hard-truncate text so it fits within max_tokens."""
    tokens = _TOKENIZER.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _TOKENIZER.decode(tokens[:max_tokens])


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_completion_prompt(
    prefix: str,
    suffix: str,
    language: SupportedLanguage,
    context_snippets: List[str],
) -> str:
    """
    Fill-in-the-middle style prompt.
    The model sees:  [context] + prefix + <FILL> + suffix
    and should output only the missing middle part.
    """
    lang_hint = "" if language == SupportedLanguage.unknown else f" ({language.value})"

    # Reserve tokens: system overhead ~100, suffix ~200, completion ~512
    available_for_prefix = settings.ollama_context_window - 100 - 200 - settings.ollama_num_predict
    available_for_context = available_for_prefix // 3  # context gets ⅓ of budget

    context_block = ""
    if context_snippets:
        joined = "\n\n---\n\n".join(context_snippets)
        joined = _truncate_to_tokens(joined, available_for_context)
        context_block = f"# Relevant code from this codebase:\n{joined}\n\n"

    prefix = _truncate_to_tokens(prefix, available_for_prefix - available_for_context)

    prompt = (
        f"You are an expert{lang_hint} programmer. "
        f"Complete the code below. Output ONLY the completion text, "
        f"no explanations, no markdown fences.\n\n"
        f"{context_block}"
        f"# Code to complete:\n"
        f"{prefix}<FILL_HERE>{suffix}\n\n"
        f"# Completion (just the missing part):\n"
    )
    return prompt


def _build_explanation_prompt(
    code: str,
    language: SupportedLanguage,
    context_before: str,
    context_after: str,
    detail_level: str,
) -> str:
    lang_hint = "" if language == SupportedLanguage.unknown else f"{language.value} "

    detail_instructions = {
        "brief":    "in 1-2 sentences",
        "standard": "in a clear paragraph",
        "detailed": "step by step, explaining each logical section",
    }
    instruction = detail_instructions.get(detail_level, "in a clear paragraph")

    context_block = ""
    if context_before.strip() or context_after.strip():
        context_block = (
            f"\n\nSurrounding context (for reference only):\n"
            f"```\n{context_before}\n[SELECTED CODE]\n{context_after}\n```"
        )

    return (
        f"You are a senior {lang_hint}developer. "
        f"Explain the following code {instruction}. "
        f"After the explanation, list up to 3 concrete improvement suggestions "
        f"as a JSON array under the key 'improvements'. "
        f"Format your response as:\n"
        f"EXPLANATION:\n<your explanation>\n\n"
        f"IMPROVEMENTS:\n<json array of strings, or empty array []>\n\n"
        f"Code to explain:\n```\n{code}\n```"
        f"{context_block}"
    )


def _build_chat_system_prompt(active_file_content: Optional[str]) -> str:
    base = (
        "You are an expert programming assistant embedded in VS Code. "
        "Answer questions about code clearly and concisely. "
        "When writing code, always use markdown code fences with the language name. "
        "Be direct — avoid unnecessary preamble."
    )
    if active_file_content:
        snippet = _truncate_to_tokens(active_file_content, 800)
        base += (
            f"\n\nThe user currently has this file open in their editor:\n"
            f"```\n{snippet}\n```\n"
            f"Reference it when relevant."
        )
    return base


# ── LLMClient ─────────────────────────────────────────────────────────────────

class LLMClient:
    """
    Async wrapper around ollama-python SDK.
    All public methods are async and safe to call from FastAPI route handlers.
    """

    def __init__(self) -> None:
        # AsyncClient handles its own httpx session internally
        self._client = ollama_sdk.AsyncClient(host=settings.ollama_base_url)
        self._model = settings.ollama_model
        logger.debug(f"LLMClient initialised — model: {self._model}")

    # ── Liveness ─────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Returns True if Ollama is reachable."""
        try:
            await self._client.list()
            return True
        except Exception as e:
            raise RuntimeError(f"Ollama unreachable: {e}")

    # ── Code completion ───────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def complete_code(
        self,
        prefix: str,
        suffix: str = "",
        language: SupportedLanguage = SupportedLanguage.unknown,
        context_snippets: Optional[List[str]] = None,
        n_completions: int = 1,
    ) -> List[str]:
        """
        Returns a list of completion strings (length == n_completions).
        For n > 1 we make parallel async calls.
        """
        prompt = _build_completion_prompt(
            prefix, suffix, language, context_snippets or []
        )

        async def _single_call() -> str:
            response = await self._client.generate(
                model=self._model,
                prompt=prompt,
                options={
                    "temperature": settings.ollama_temperature,
                    "num_predict": settings.ollama_num_predict,
                    "stop": ["# Code to complete:", "```", "\n\n\n"],
                },
                stream=False,
            )
            return response.response.strip()

        tasks = [_single_call() for _ in range(n_completions)]
        results = await asyncio.gather(*tasks)
        logger.debug(f"Generated {len(results)} completion(s)")
        return list(results)

    # ── Code explanation ──────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def explain_code(
        self,
        code: str,
        language: SupportedLanguage = SupportedLanguage.unknown,
        context_before: str = "",
        context_after: str = "",
        detail_level: str = "standard",
    ) -> dict:
        """
        Returns a dict with keys:
          explanation (str)
          improvements (List[str])
        """
        import json, re

        prompt = _build_explanation_prompt(
            code, language, context_before, context_after, detail_level
        )

        response = await self._client.generate(
            model=self._model,
            prompt=prompt,
            options={
                "temperature": 0.3,
                "num_predict": 1024,
            },
            stream=False,
        )
        raw = response.response.strip()

        # Parse structured response
        explanation = raw
        improvements: List[str] = []

        if "EXPLANATION:" in raw and "IMPROVEMENTS:" in raw:
            parts = raw.split("IMPROVEMENTS:")
            explanation = parts[0].replace("EXPLANATION:", "").strip()
            improvements_raw = parts[1].strip()
            # Extract JSON array
            match = re.search(r"\[.*?\]", improvements_raw, re.DOTALL)
            if match:
                try:
                    improvements = json.loads(match.group())
                except json.JSONDecodeError:
                    improvements = []

        return {"explanation": explanation, "improvements": improvements}

    # ── Chat (single turn, no streaming) ─────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def chat(
        self,
        messages: List[ChatMessage],
        active_file_content: Optional[str] = None,
    ) -> str:
        """Single-turn chat response (full string, not streamed)."""
        system_prompt = _build_chat_system_prompt(active_file_content)

        ollama_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            ollama_messages.append({"role": msg.role.value, "content": msg.content})

        response = await self._client.chat(
            model=self._model,
            messages=ollama_messages,
            options={
                "temperature": 0.4,
                "num_predict": 1024,
            },
            stream=False,
        )
        if hasattr(response, 'message'):
            return response.message.content.strip()
        elif isinstance(response, dict):
            return response.get('message', {}).get('content', '').strip()
        return str(response)

    # ── Chat (streaming) ─────────────────────────────────────────────────────

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        active_file_content: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator — yields token strings one by one.
        Used by the SSE endpoint in explanation.py for the chat panel.
        """
        system_prompt = _build_chat_system_prompt(active_file_content)

        ollama_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            ollama_messages.append({"role": msg.role.value, "content": msg.content})

        async for chunk in await self._client.chat(
            model=self._model,
            messages=ollama_messages,
            options={"temperature": 0.4, "num_predict": 1024},
            stream=True,
        ):
            token = chunk.message.content
            if token:
                yield token
