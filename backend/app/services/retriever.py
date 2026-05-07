"""
backend/app/services/retriever.py
───────────────────────────────────
ChromaDB wrapper — the vector store layer.

Responsibilities:
  - Create / open the persistent ChromaDB collection on startup
  - Upsert code chunks with metadata (filepath, lines, language)
  - Query by embedding vector → ranked SearchResultItem list
  - Delete all chunks belonging to a specific file (used on re-index)
  - Count total indexed chunks (exposed via /health)
  - Persist the store to disk (called on shutdown)

ChromaDB stores data in the directory set by CHROMA_PERSIST_DIR in .env.
On first run it creates the directory; subsequent runs load from disk.
"""

import hashlib
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from app.config import settings
from app.models.schemas import SearchResultItem, SupportedLanguage
from app.services.embedder import EmbedderService


def _make_chunk_id(filepath: str, start_line: int, content: str) -> str:
    """
    Deterministic chunk ID based on file path + line number + content hash.
    Using a deterministic ID means upsert() is idempotent — re-indexing the
    same unchanged file is a no-op at the ChromaDB level.
    """
    digest = hashlib.md5(content.encode()).hexdigest()[:8]
    safe_path = filepath.replace("\\", "/").replace(":", "")
    return f"{safe_path}:{start_line}:{digest}"


class RetrieverService:
    """
    Singleton-style service; instantiated once in main.py lifespan and stored
    on app.state.retriever.  Route handlers receive it via dependency injection.
    """

    def __init__(self, embedder: EmbedderService) -> None:
        self._embedder = embedder

        # PersistentClient automatically loads existing data from disk
        self._client = chromadb.PersistentClient(
            path=str(settings.chroma_persist_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # get_or_create_collection: safe on first run AND on restart
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection_name,
            # cosine distance — our embeddings are unit-normalised so this
            # is equivalent to cosine similarity
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"ChromaDB collection '{settings.chroma_collection_name}' "
            f"loaded — {self._collection.count()} chunks"
        )

    # ── Write operations ──────────────────────────────────────────────────────

    def upsert_file(
        self,
        filepath: str,
        language: SupportedLanguage,
        chunks: List[dict],  # each: {content, start_line, end_line}
    ) -> int:
        """
        Index (or re-index) all chunks from a single file.
        Returns the number of chunks actually upserted.

        Steps:
          1. Delete any existing chunks for this file (handles file edits)
          2. Embed all chunks in one batch call
          3. Upsert into ChromaDB
        """
        if not chunks:
            return 0

        # 1. Remove stale chunks for this file
        self.delete_file(filepath)

        # 2. Build parallel lists: ids, embeddings, documents, metadatas
        ids         = []
        documents   = []
        metadatas   = []

        for chunk in chunks:
            chunk_id = _make_chunk_id(filepath, chunk["start_line"], chunk["content"])
            ids.append(chunk_id)
            documents.append(chunk["content"])
            metadatas.append({
                "filepath":   filepath,
                "language":   language.value,
                "start_line": chunk["start_line"],
                "end_line":   chunk["end_line"],
            })

        # 3. Batch embed
        embeddings = self._embedder.encode_batch(documents)

        # 4. Upsert
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug(f"Upserted {len(ids)} chunks for {filepath}")
        return len(ids)

    def delete_file(self, filepath: str) -> None:
        """Remove all indexed chunks that belong to filepath."""
        try:
            results = self._collection.get(
                where={"filepath": filepath},
                include=[],  # we only need IDs
            )
            if results["ids"]:
                self._collection.delete(ids=results["ids"])
                logger.debug(f"Deleted {len(results['ids'])} stale chunks for {filepath}")
        except Exception as e:
            # Non-fatal — log and continue
            logger.warning(f"Could not delete chunks for {filepath}: {e}")

    # ── Read operations ───────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        top_k: Optional[int] = None,
        filter_languages: Optional[List[SupportedLanguage]] = None,
        filter_filepath_prefix: Optional[str] = None,
    ) -> List[SearchResultItem]:
        """
        Embed query_text and return the top_k most similar code chunks.

        ChromaDB's query() returns distances in [0, 2] for cosine space.
        We convert to similarity score in [0, 1]:  score = 1 - distance/2
        """
        n_results = top_k or settings.search_top_k

        # Build optional metadata filter
        where: Optional[dict] = None
        conditions = []

        if filter_languages:
            lang_values = [lang.value for lang in filter_languages]
            if len(lang_values) == 1:
                conditions.append({"language": {"$eq": lang_values[0]}})
            else:
                conditions.append({"language": {"$in": lang_values}})

        if filter_filepath_prefix:
            conditions.append({"filepath": {"$contains": filter_filepath_prefix}})

        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        query_embedding = self._embedder.encode(query_text)

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, self._collection.count() or 1),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return []

        items: List[SearchResultItem] = []
        if not results["ids"] or not results["ids"][0]:
            return items

        for i, chunk_id in enumerate(results["ids"][0]):
            meta     = results["metadatas"][0][i]
            doc      = results["documents"][0][i]
            distance = results["distances"][0][i]
            score    = round(1.0 - distance / 2.0, 4)  # cosine distance → similarity

            items.append(SearchResultItem(
                chunk_id   = chunk_id,
                content    = doc,
                filepath   = meta["filepath"],
                start_line = int(meta["start_line"]),
                end_line   = int(meta["end_line"]),
                language   = SupportedLanguage(meta.get("language", "unknown")),
                score      = max(0.0, min(1.0, score)),
            ))

        return items

    # ── Utility ───────────────────────────────────────────────────────────────

    def count(self) -> int:
        """Total number of indexed chunks. Used by /health."""
        try:
            return self._collection.count()
        except Exception:
            return 0

    def persist(self) -> None:
        """
        PersistentClient auto-persists on every write, but we call this
        explicitly on graceful shutdown for safety.
        """
        # chromadb.PersistentClient doesn't expose an explicit persist() call
        # in 0.5.x — data is written to disk automatically.
        logger.info("ChromaDB data persisted to disk.")
