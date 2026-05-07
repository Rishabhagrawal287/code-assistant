"""
backend/app/models/schemas.py
──────────────────────────────
All Pydantic v2 request/response models for every API endpoint.

Keeping schemas in one file means:
  • Easy to see the full API surface at a glance
  • No circular imports between route modules
  • TypeScript types in the VS Code extension can be generated from these

Sections:
  1. Shared / base types
  2. Code Completion  (/completion/*)
  3. Semantic Search  (/search/*)
  4. Code Explanation (/explanation/*)
  5. Chat             (/chat/*)
  6. Indexing         (/index/*)
  7. Health           (/health)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# 1. Shared / base types
# ─────────────────────────────────────────────────────────────────────────────

class SupportedLanguage(str, Enum):
    """
    Languages the backend explicitly supports for parsing hints.
    'unknown' is the safe fallback – the LLM still works, just without
    language-specific prompt engineering.
    """
    python = "python"
    javascript = "javascript"
    typescript = "typescript"
    java = "java"
    cpp = "cpp"
    c = "c"
    go = "go"
    rust = "rust"
    ruby = "ruby"
    php = "php"
    unknown = "unknown"


class CodeSnippet(BaseModel):
    """A reusable block representing a piece of source code with metadata."""
    content: str = Field(..., description="The raw source code text.")
    language: SupportedLanguage = Field(
        SupportedLanguage.unknown,
        description="Programming language of the snippet.",
    )
    filepath: Optional[str] = Field(
        None,
        description="Absolute or workspace-relative file path (used for context).",
    )
    start_line: Optional[int] = Field(
        None, ge=1, description="1-based line number where the snippet starts."
    )
    end_line: Optional[int] = Field(
        None, ge=1, description="1-based line number where the snippet ends."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Code Completion  POST /completion/inline
# ─────────────────────────────────────────────────────────────────────────────

class CompletionRequest(BaseModel):
    """
    Sent by the VS Code InlineCompletionItemProvider each time the user
    pauses typing (debounced on the extension side).
    """
    prefix: str = Field(
        ...,
        description="All code BEFORE the cursor in the current file.",
    )
    suffix: str = Field(
        "",
        description="All code AFTER the cursor (for fill-in-the-middle models).",
    )
    language: SupportedLanguage = Field(SupportedLanguage.unknown)
    filepath: Optional[str] = Field(None)
    # How many alternative completions to return (extension shows top-1 inline)
    n_completions: int = Field(1, ge=1, le=5)
    # Optional: extra context snippets retrieved from semantic search
    context_snippets: List[str] = Field(
        default_factory=list,
        description="Relevant code chunks from the codebase, injected into the prompt.",
    )

    @field_validator("prefix")
    @classmethod
    def prefix_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("prefix must contain at least one non-whitespace character")
        return v


class CompletionChoice(BaseModel):
    text: str = Field(..., description="The suggested completion text.")
    # Tokens used; helpful for debugging context-window issues
    tokens_used: Optional[int] = None


class CompletionResponse(BaseModel):
    choices: List[CompletionChoice]
    model: str = Field(..., description="Ollama model that generated the completion.")
    cached: bool = Field(False, description="True if served from a short-term LRU cache.")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Semantic Search  POST /search/similar
# ─────────────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """
    Query for finding code similar to a given snippet or natural-language
    description in the indexed codebase.
    """
    query: str = Field(
        ...,
        min_length=3,
        description="Either a code snippet or a natural-language question.",
    )
    top_k: Optional[int] = Field(
        None,
        ge=1,
        le=20,
        description="Override the default SEARCH_TOP_K from config.",
    )
    # Optionally restrict search to specific languages
    filter_languages: List[SupportedLanguage] = Field(default_factory=list)
    # Optionally restrict search to files under a path prefix
    filter_filepath_prefix: Optional[str] = None


class SearchResultItem(BaseModel):
    """One matching code chunk returned by ChromaDB."""
    chunk_id: str = Field(..., description="Unique ID of this chunk in ChromaDB.")
    content: str = Field(..., description="The matching source code chunk.")
    filepath: str
    start_line: int
    end_line: int
    language: SupportedLanguage
    # Cosine similarity score [0, 1]; higher = more similar
    score: float = Field(..., ge=0.0, le=1.0)


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    query: str
    total_indexed_chunks: int = Field(
        ..., description="Total number of chunks currently in the vector store."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Code Explanation  POST /explanation/explain
# ─────────────────────────────────────────────────────────────────────────────

class ExplanationRequest(BaseModel):
    """
    Triggered by the "Explain This Code" right-click command in VS Code.
    The extension sends the selected text + surrounding context.
    """
    code: str = Field(..., min_length=1, description="The selected code to explain.")
    language: SupportedLanguage = Field(SupportedLanguage.unknown)
    filepath: Optional[str] = None
    # Optional surrounding context to help the LLM understand imports/scope
    context_before: str = Field(
        "",
        description="Lines immediately before the selection (e.g. 10 lines).",
    )
    context_after: str = Field(
        "",
        description="Lines immediately after the selection.",
    )
    # Style of explanation the user wants
    detail_level: str = Field(
        "standard",
        pattern="^(brief|standard|detailed)$",
        description="'brief' = 1–2 sentences, 'standard' = paragraph, 'detailed' = step-by-step.",
    )


class ExplanationResponse(BaseModel):
    explanation: str = Field(..., description="Human-readable explanation of the code.")
    suggested_improvements: List[str] = Field(
        default_factory=list,
        description="Optional list of improvement suggestions from the LLM.",
    )
    model: str


# ─────────────────────────────────────────────────────────────────────────────
# 5. Chat  POST /chat/message
# ─────────────────────────────────────────────────────────────────────────────

class ChatRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    """
    Sent by the sidebar chat panel.  The full conversation history is included
    so the backend can maintain context without server-side session state.
    """
    messages: List[ChatMessage] = Field(..., min_length=1)
    # Current file open in the editor – injected as context
    active_file: Optional[CodeSnippet] = None
    # If True, stream tokens back via SSE (Server-Sent Events)
    stream: bool = Field(False)


class ChatResponse(BaseModel):
    message: ChatMessage
    model: str
    # Number of tokens in the entire conversation sent to the model
    prompt_tokens: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Indexing  POST /index/files
# ─────────────────────────────────────────────────────────────────────────────

class IndexRequest(BaseModel):
    """
    Asks the backend to (re)index a list of source files.
    The VS Code extension calls this on workspace open and on file save.
    """
    files: List[IndexFileItem] = Field(..., min_length=1)
    # If True, wipe & rebuild the collection; otherwise upsert only changed files
    full_reindex: bool = Field(False)


class IndexFileItem(BaseModel):
    filepath: str = Field(..., description="Absolute path on the user's machine.")
    content: str = Field(..., description="Full text of the file.")
    language: SupportedLanguage = Field(SupportedLanguage.unknown)


class IndexResponse(BaseModel):
    indexed_files: int
    total_chunks: int
    skipped_files: int = Field(0, description="Files skipped because content is unchanged.")
    errors: List[Dict[str, Any]] = Field(default_factory=list)


# Fix forward reference (IndexRequest references IndexFileItem defined after it)
IndexRequest.model_rebuild()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Health  GET /health
# ─────────────────────────────────────────────────────────────────────────────

class ServiceStatus(str, Enum):
    ok = "ok"
    degraded = "degraded"
    unavailable = "unavailable"


class HealthResponse(BaseModel):
    status: ServiceStatus
    ollama: ServiceStatus
    chromadb: ServiceStatus
    embedding_model: ServiceStatus
    ollama_model: str
    indexed_chunks: int
    version: str = "0.1.0"
