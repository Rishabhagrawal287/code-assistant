"""
backend/app/main.py
────────────────────
FastAPI application factory.

Responsibilities:
  - Creates the FastAPI app instance
  - Registers CORS middleware (required for VS Code webview origin)
  - Manages lifespan: warms up the embedder and ChromaDB on startup
  - Mounts all route prefixes
  - Exposes GET /health for the extension status bar
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.models.schemas import HealthResponse, ServiceStatus
from app.routes import completion, explanation, search
from app.services.embedder import EmbedderService
from app.services.llm_client import LLMClient
from app.services.retriever import RetrieverService


# ── Lifespan: runs once on startup, once on shutdown ─────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Warm up all heavy services before the first request arrives.
    Storing them on app.state makes them accessible inside route handlers
    via   request.app.state.<service>
    """
    logger.info("🚀  Starting Code Assistant backend...")

    # 1. Embedding model (downloads ~90 MB on first run, cached after)
    logger.info(f"Loading embedding model: {settings.embedding_model}")
    app.state.embedder = EmbedderService()
    logger.info("✅  Embedder ready")

    # 2. ChromaDB (creates persist directory if needed)
    logger.info(f"Connecting to ChromaDB at: {settings.chroma_persist_path}")
    app.state.retriever = RetrieverService(embedder=app.state.embedder)
    logger.info(f"✅  ChromaDB ready — collection: {settings.chroma_collection_name}")

    # 3. Ollama LLM client (lightweight, just sets up httpx session)
    logger.info(f"Initialising Ollama client — model: {settings.ollama_model}")
    app.state.llm = LLMClient()
    logger.info("✅  LLM client ready")

    logger.info(f"🟢  Backend listening on http://{settings.host}:{settings.port}")
    yield  # ← server is live and handling requests here

    # Shutdown
    logger.info("🔴  Shutting down — persisting ChromaDB...")
    # ChromaDB PersistentClient auto-persists; explicit call for safety
    app.state.retriever.persist()
    logger.info("👋  Shutdown complete")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Code Assistant API",
        description=(
            "Local AI-powered code assistant backend. "
            "Powered by Ollama (LLM) + ChromaDB (vector search) + "
            "sentence-transformers (embeddings). All free, all local."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",       # Swagger UI at http://localhost:8000/docs
        redoc_url="/redoc",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    # VS Code webviews use the origin  vscode-webview://<id>
    # We also allow localhost for manual testing via browser / curl
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=r"vscode-webview://.*",  # any webview id
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(completion.router,  prefix="/completion",  tags=["Completion"])
    app.include_router(search.router,      prefix="/search",      tags=["Search"])
    app.include_router(explanation.router, prefix="/explanation", tags=["Explanation"])

    return app


app = create_app()


# ── Health endpoint ───────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """
    Called by the VS Code extension every 30 s to update the status bar icon.
    Checks liveness of each sub-service without doing any real work.
    """
    ollama_status = ServiceStatus.unavailable
    chroma_status = ServiceStatus.unavailable
    embed_status  = ServiceStatus.unavailable
    indexed_chunks = 0

    # Check Ollama
    try:
        llm: LLMClient = app.state.llm
        await llm.ping()
        ollama_status = ServiceStatus.ok
    except Exception as e:
        logger.warning(f"Ollama health check failed: {e}")

    # Check ChromaDB + get chunk count
    try:
        retriever: RetrieverService = app.state.retriever
        indexed_chunks = retriever.count()
        chroma_status = ServiceStatus.ok
    except Exception as e:
        logger.warning(f"ChromaDB health check failed: {e}")

    # Check embedder
    try:
        embedder: EmbedderService = app.state.embedder
        embedder.ping()
        embed_status = ServiceStatus.ok
    except Exception as e:
        logger.warning(f"Embedder health check failed: {e}")

    overall = (
        ServiceStatus.ok
        if all(s == ServiceStatus.ok for s in [ollama_status, chroma_status, embed_status])
        else ServiceStatus.degraded
    )

    return HealthResponse(
        status=overall,
        ollama=ollama_status,
        chromadb=chroma_status,
        embedding_model=embed_status,
        ollama_model=settings.ollama_model,
        indexed_chunks=indexed_chunks,
    )


# ── Dev entrypoint ────────────────────────────────────────────────────────────
# Run with:  python -m app.main   (from backend/ with venv active)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )
