"""
backend/app/config.py
─────────────────────
Single source of truth for every runtime setting.

Pydantic-Settings reads values in this priority order:
  1. Real environment variables (e.g. export OLLAMA_MODEL=...)
  2. .env file next to the backend/ directory
  3. Default values defined here

Usage anywhere in the app:
    from app.config import settings
    print(settings.ollama_model)
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Pydantic-Settings config ──────────────────────────────────────────────
    model_config = SettingsConfigDict(
        # Look for .env relative to this file's grandparent (backend/)
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",            # silently drop unknown env vars
    )

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True

    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "deepseek-coder:6.7b"
    ollama_temperature: float = 0.2
    ollama_num_predict: int = 512
    ollama_context_window: int = 4096

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_store"
    chroma_collection_name: str = "codebase"

    # ── Code Search ───────────────────────────────────────────────────────────
    search_top_k: int = 5
    chunk_size: int = 200
    chunk_overlap: int = 40

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Stored as a raw string in .env; parsed into a list below.
    cors_origins: str = "vscode-webview://,http://localhost:3000"

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a clean list, stripping whitespace."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ollama_generate_url(self) -> str:
        """Full URL for Ollama's /api/generate endpoint."""
        return f"{self.ollama_base_url}/api/generate"

    @property
    def ollama_chat_url(self) -> str:
        """Full URL for Ollama's /api/chat endpoint (used for the chat panel)."""
        return f"{self.ollama_base_url}/api/chat"

    @property
    def chroma_persist_path(self) -> Path:
        """Resolved absolute path for the ChromaDB store."""
        p = Path(self.chroma_persist_dir)
        if not p.is_absolute():
            # Resolve relative to backend/ (two levels up from this file)
            p = Path(__file__).resolve().parents[1] / p
        p.mkdir(parents=True, exist_ok=True)
        return p


# ── Module-level singleton ─────────────────────────────────────────────────────
# @lru_cache ensures the .env file is read exactly once per process.
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenience alias – import this everywhere:
#   from app.config import settings
settings: Settings = get_settings()
