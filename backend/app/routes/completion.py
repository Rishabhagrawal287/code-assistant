"""
backend/app/routes/completion.py
──────────────────────────────────
POST /completion/inline  — AI code completion endpoint.

Flow:
  1. Receive prefix + suffix + language from the VS Code extension
  2. (Optional) Run a quick semantic search to find relevant codebase context
  3. Build a fill-in-the-middle prompt and call Ollama
  4. Return ranked completion choices

The extension calls this endpoint from its InlineCompletionItemProvider,
debounced to ~500 ms after the user stops typing.
"""

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app.models.schemas import (
    CompletionChoice,
    CompletionRequest,
    CompletionResponse,
)
from app.services.llm_client import LLMClient
from app.services.retriever import RetrieverService

router = APIRouter()


@router.post("/inline", response_model=CompletionResponse)
async def inline_completion(request: Request, body: CompletionRequest) -> CompletionResponse:
    """
    Generate inline code completion(s) for the code at the cursor position.

    - prefix: everything before the cursor in the active file
    - suffix: everything after the cursor (used for fill-in-the-middle)
    - context_snippets: optional pre-fetched relevant chunks (client can provide
      these to skip the server-side search and save latency)
    """
    llm: LLMClient           = request.app.state.llm
    retriever: RetrieverService = request.app.state.retriever

    # ── Optional: auto-fetch context if none provided ─────────────────────────
    context_snippets = list(body.context_snippets)  # copy so we can append

    if not context_snippets and retriever.count() > 0:
        # Use the last ~200 chars of prefix as the semantic search query
        search_query = body.prefix[-200:].strip()
        if search_query:
            similar = retriever.query(query_text=search_query, top_k=3)
            context_snippets = [item.content for item in similar]
            logger.debug(f"Auto-fetched {len(context_snippets)} context snippets")

    # ── Call LLM ──────────────────────────────────────────────────────────────
    try:
        raw_completions = await llm.complete_code(
            prefix=body.prefix,
            suffix=body.suffix,
            language=body.language,
            context_snippets=context_snippets,
            n_completions=body.n_completions,
        )
    except Exception as e:
        logger.error(f"LLM completion error: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"LLM unavailable: {str(e)}. Is Ollama running?",
        )

    choices = [CompletionChoice(text=text) for text in raw_completions if text.strip()]

    if not choices:
        # Return empty rather than 500 — the extension handles empty gracefully
        choices = [CompletionChoice(text="")]

    return CompletionResponse(
        choices=choices,
        model=llm._model,
        cached=False,
    )
