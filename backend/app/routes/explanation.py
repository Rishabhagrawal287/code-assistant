"""
backend/app/routes/explanation.py
───────────────────────────────────
Two endpoints:

  POST /explanation/explain  — explain selected code (right-click command)
  POST /explanation/chat     — multi-turn chat (sidebar chat panel)
  POST /explanation/chat/stream — streaming version via Server-Sent Events

The streaming endpoint is what the sidebar webview uses so the user sees
tokens appear one by one instead of waiting for the full response.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from app.models.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatRole,
    ExplanationRequest,
    ExplanationResponse,
)
from app.services.llm_client import LLMClient

router = APIRouter()


# ── POST /explanation/explain ─────────────────────────────────────────────────

@router.post("/explain", response_model=ExplanationResponse)
async def explain_code(request: Request, body: ExplanationRequest) -> ExplanationResponse:
    """
    Triggered by the "Explain This Code" right-click context menu command.

    The extension sends:
      - code: the selected text
      - language: detected from file extension
      - context_before / context_after: surrounding lines for scope awareness
      - detail_level: 'brief' | 'standard' | 'detailed'
    """
    llm: LLMClient = request.app.state.llm

    try:
        result = await llm.explain_code(
            code=body.code,
            language=body.language,
            context_before=body.context_before,
            context_after=body.context_after,
            detail_level=body.detail_level,
        )
    except Exception as e:
        logger.error(f"Explanation error: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"LLM unavailable: {str(e)}. Is Ollama running?",
        )

    return ExplanationResponse(
        explanation=result["explanation"],
        suggested_improvements=result["improvements"],
        model=llm._model,
    )


# ── POST /explanation/chat ────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Non-streaming chat endpoint.
    Returns the full assistant reply in one JSON response.
    Use this for quick integrations or when SSE is not available.
    """
    llm: LLMClient = request.app.state.llm

    active_file_content = (
        body.active_file.content if body.active_file else None
    )

    try:
        reply_text = await llm.chat(
            messages=body.messages,
            active_file_content=active_file_content,
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"LLM unavailable: {str(e)}. Is Ollama running?",
        )

    reply_message = ChatMessage(role=ChatRole.assistant, content=reply_text)

    return ChatResponse(
        message=reply_message,
        model=llm._model,
    )


# ── POST /explanation/chat/stream ─────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """
    Streaming chat endpoint using Server-Sent Events (SSE).

    The VS Code sidebar webview connects here and receives tokens one by one.
    Each SSE event is a JSON object:

      data: {"token": "Hello"}\\n\\n
      data: {"token": " world"}\\n\\n
      data: {"done": true, "model": "deepseek-coder:6.7b"}\\n\\n

    The webview appends each token to the chat bubble in real time.
    """
    llm: LLMClient = request.app.state.llm
    active_file_content = body.active_file.content if body.active_file else None

    async def event_generator():
        try:
            async for token in llm.chat_stream(
                messages=body.messages,
                active_file_content=active_file_content,
            ):
                # Format as SSE
                payload = json.dumps({"token": token})
                yield f"data: {payload}\n\n"
                # Small yield to the event loop — keeps the connection alive
                await asyncio.sleep(0)

            # Send done signal
            done_payload = json.dumps({"done": True, "model": llm._model})
            yield f"data: {done_payload}\n\n"

        except asyncio.CancelledError:
            # Client disconnected — clean exit
            logger.debug("SSE client disconnected")
        except Exception as e:
            logger.error(f"Streaming chat error: {e}")
            error_payload = json.dumps({"error": str(e)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering if behind proxy
        },
    )
