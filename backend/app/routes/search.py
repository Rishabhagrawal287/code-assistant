"""
backend/app/routes/search.py
──────────────────────────────
Two endpoints:

  POST /search/similar   — find code chunks similar to a query
  POST /index/files      — index (or re-index) source files into ChromaDB

The VS Code extension calls /index/files:
  - When the workspace is first opened
  - When a file is saved (sends just that one file)
  - When the user manually triggers "Re-index Workspace" from the command palette
"""

from typing import List

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app.models.schemas import (
    IndexFileItem,
    IndexRequest,
    IndexResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.embedder import EmbedderService
from app.services.retriever import RetrieverService

router = APIRouter()


# ── POST /search/similar ──────────────────────────────────────────────────────

@router.post("/similar", response_model=SearchResponse)
async def search_similar(request: Request, body: SearchRequest) -> SearchResponse:
    """
    Semantic code search.

    Accepts either:
      - A natural-language question:  "function that parses JSON config"
      - A code snippet:               "def load_config(path):"

    Returns the top-k most semantically similar chunks from the indexed codebase.
    """
    retriever: RetrieverService = request.app.state.retriever

    if retriever.count() == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "No files are indexed yet. "
                "Open a workspace in VS Code and wait for indexing to complete, "
                "or call POST /index/files first."
            ),
        )

    results = retriever.query(
        query_text=body.query,
        top_k=body.top_k,
        filter_languages=body.filter_languages or None,
        filter_filepath_prefix=body.filter_filepath_prefix,
    )

    return SearchResponse(
        results=results,
        query=body.query,
        total_indexed_chunks=retriever.count(),
    )


# ── POST /index/files ─────────────────────────────────────────────────────────

@router.post("/index/files", response_model=IndexResponse, tags=["Index"])
async def index_files(request: Request, body: IndexRequest) -> IndexResponse:
    """
    Index one or more source files into ChromaDB.

    Each file is:
      1. Split into overlapping line-based chunks (size/overlap from config)
      2. Embedded in a single batch call to sentence-transformers
      3. Upserted into ChromaDB (idempotent — unchanged chunks are no-ops)

    If full_reindex=True the entire collection is dropped and rebuilt.
    Use full_reindex sparingly — it's slow for large codebases.
    """
    embedder:  EmbedderService  = request.app.state.embedder
    retriever: RetrieverService = request.app.state.retriever

    # Full reindex: wipe collection first
    if body.full_reindex:
        logger.info("Full reindex requested — clearing ChromaDB collection")
        try:
            from app.config import settings
            from chromadb.config import Settings as ChromaSettings
            import chromadb

            retriever._client.delete_collection(settings.chroma_collection_name)
            retriever._collection = retriever._client.get_or_create_collection(
                name=settings.chroma_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Collection cleared")
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            raise HTTPException(status_code=500, detail=f"Full reindex failed: {e}")

    indexed_files  = 0
    total_chunks   = 0
    skipped_files  = 0
    errors: List[dict] = []

    for file_item in body.files:
        try:
            # Skip empty or binary-looking files
            if not file_item.content.strip():
                skipped_files += 1
                continue

            # Chunk the file into overlapping line windows
            chunks = embedder.chunk_code_with_lines(file_item.content)
            if not chunks:
                skipped_files += 1
                continue

            n_upserted = retriever.upsert_file(
                filepath=file_item.filepath,
                language=file_item.language,
                chunks=chunks,
            )
            indexed_files += 1
            total_chunks  += n_upserted
            logger.debug(f"Indexed {file_item.filepath}: {n_upserted} chunks")

        except Exception as e:
            logger.error(f"Error indexing {file_item.filepath}: {e}")
            errors.append({"filepath": file_item.filepath, "error": str(e)})

    logger.info(
        f"Indexing complete — {indexed_files} files, "
        f"{total_chunks} chunks, {skipped_files} skipped, {len(errors)} errors"
    )

    return IndexResponse(
        indexed_files=indexed_files,
        total_chunks=total_chunks,
        skipped_files=skipped_files,
        errors=errors,
    )
