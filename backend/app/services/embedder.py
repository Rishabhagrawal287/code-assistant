"""
backend/app/services/embedder.py
──────────────────────────────────
Wrapper around sentence-transformers for generating code embeddings.

Responsibilities:
  - Load the embedding model once at startup (held in app.state)
  - Encode single strings and batches of strings → numpy float32 vectors
  - Expose a ping() for the health check endpoint
  - Normalise vectors to unit length (required for cosine similarity in ChromaDB)

Why sentence-transformers/all-MiniLM-L6-v2?
  - 384-dimensional vectors — small enough to be fast on CPU
  - Decent semantic understanding of code and natural language
  - Ships inside the sentence-transformers package you already have installed
  - Better code-specific option: 'flax-sentence-embeddings/st-codesearch-distilroberta-base'
    (swap in .env EMBEDDING_MODEL= if you want to try it)
"""

from typing import List, Union

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from app.config import settings


class EmbedderService:
    """
    Singleton-style service; instantiated once in main.py lifespan and stored
    on app.state.embedder.  Route handlers receive it via dependency injection.
    """

    def __init__(self) -> None:
        logger.info(f"Loading SentenceTransformer: {settings.embedding_model}")
        self._model = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
        # Warm-up pass — forces the model to compile/load weights fully
        _ = self._model.encode(["warmup"], normalize_embeddings=True)
        self._dim = self._model.get_sentence_embedding_dimension()
        logger.info(f"Embedder ready — dimension: {self._dim}, device: {settings.embedding_device}")

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def dimension(self) -> int:
        """Embedding vector dimension (384 for all-MiniLM-L6-v2)."""
        return self._dim

    # ── Core encode methods ───────────────────────────────────────────────────

    def encode(self, text: str) -> List[float]:
        """
        Encode a single string → normalised float list.
        Used for query-time embedding (search requests, completions with context).
        """
        vector: np.ndarray = self._model.encode(
            text,
            normalize_embeddings=True,  # unit-length → cosine sim == dot product
            show_progress_bar=False,
        )
        return vector.tolist()

    def encode_batch(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """
        Encode multiple strings in one pass — much faster than encoding one by one.
        Used during file indexing.

        Returns a list of float lists, same order as input.
        """
        if not texts:
            return []

        logger.debug(f"Encoding batch of {len(texts)} texts (batch_size={batch_size})")
        vectors: np.ndarray = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 100,  # only show bar for large batches
            convert_to_numpy=True,
        )
        return vectors.tolist()

    # ── Utilities ─────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """
        Lightweight liveness check used by GET /health.
        Encodes a trivial string and checks the output shape.
        """
        vec = self._model.encode(["ping"], normalize_embeddings=True)
        assert vec.shape == (1, self._dim), "Unexpected embedding shape"
        return True

    @staticmethod
    def chunk_code(
        code: str,
        chunk_size: int = None,
        overlap: int = None,
    ) -> List[str]:
        """
        Split source code into overlapping token-based chunks for indexing.

        We split on *lines* (not tokens) for simplicity — a line-based chunker
        is easier to map back to line numbers in SearchResultItem.

        chunk_size  – number of lines per chunk  (default: from config)
        overlap     – lines shared between consecutive chunks (default: from config)
        """
        chunk_size = chunk_size or settings.chunk_size
        overlap    = overlap    or settings.chunk_overlap

        lines = code.splitlines()
        if not lines:
            return []

        chunks: List[str] = []
        step = max(1, chunk_size - overlap)

        for start in range(0, len(lines), step):
            end = min(start + chunk_size, len(lines))
            chunk = "\n".join(lines[start:end])
            if chunk.strip():          # skip empty / whitespace-only chunks
                chunks.append(chunk)
            if end == len(lines):
                break

        return chunks

    @staticmethod
    def chunk_code_with_lines(
        code: str,
        chunk_size: int = None,
        overlap: int = None,
    ) -> List[dict]:
        """
        Like chunk_code() but also returns start/end line numbers.
        Returns list of dicts:  {content, start_line, end_line}
        start_line and end_line are 1-based.
        """
        chunk_size = chunk_size or settings.chunk_size
        overlap    = overlap    or settings.chunk_overlap

        lines = code.splitlines()
        if not lines:
            return []

        result = []
        step = max(1, chunk_size - overlap)

        for start in range(0, len(lines), step):
            end = min(start + chunk_size, len(lines))
            chunk = "\n".join(lines[start:end])
            if chunk.strip():
                result.append({
                    "content":    chunk,
                    "start_line": start + 1,       # 1-based
                    "end_line":   end,              # inclusive, 1-based
                })
            if end == len(lines):
                break

        return result
