"""FastAPI application: chat, session history, analytics and health.

Heavy components (embedding model, reranker, LLM client) are built once
at startup via the lifespan hook and shared across requests.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.analytics.metrics import ConversationAnalytics
from src.config import get_settings
from src.ingestion.embedder import EmbeddingService
from src.llm.base import LLMError
from src.llm.factory import LLMProviderFactory
from src.observability import setup_tracing
from src.repositories.conversation_repository import ConversationRepository
from src.repositories.vector_repository import VectorRepository
from src.retrieval.strategies import build_retrieval_strategy
from src.services.chat_service import ChatService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_tracing(settings)
    conversations = ConversationRepository(settings.history_db_path)

    condenser = None
    if settings.condense_enabled:
        condenser_settings = settings.model_copy(
            update={"llm_model": settings.condense_model, "llm_max_tokens": 120}
        )
        condenser = LLMProviderFactory.create(condenser_settings)

    state["chat_service"] = ChatService(
        retrieval=build_retrieval_strategy(
            settings,
            EmbeddingService(settings.embedding_model),
            VectorRepository(settings.qdrant_url, settings.qdrant_collection),
        ),
        llm=LLMProviderFactory.create(settings),
        conversations=conversations,
        history_window_n=settings.history_window_n,
        condenser=condenser,
    )
    state["conversations"] = conversations
    state["analytics"] = ConversationAnalytics(conversations)
    logger.info("API ready (history window N=%d)", settings.history_window_n)
    yield
    state.clear()


app = FastAPI(title="Bank RAG Assistant", version="0.1.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)


class ChatResponseBody(BaseModel):
    answer: str
    sources: list[str]
    latency_ms: int


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.post("/chat", response_model=ChatResponseBody)
def chat(body: ChatRequest) -> ChatResponseBody:
    response = state["chat_service"].ask(body.session_id, body.message)
    return ChatResponseBody(
        answer=response.answer, sources=response.sources, latency_ms=response.latency_ms
    )


@app.get("/sessions")
def list_sessions() -> dict:
    return {"sessions": state["conversations"].session_ids()}


@app.get("/sessions/{session_id}/history")
def session_history(session_id: str) -> dict:
    history = state["conversations"].full_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"No history for session '{session_id}'")
    return {"session_id": session_id, "messages": history}


@app.get("/analytics/summary")
def analytics_summary() -> dict:
    return state["analytics"].summary()


@app.get("/config")
def config_info() -> dict:
    """Safe-to-expose runtime configuration (shown in the UI sidebar)."""
    settings = get_settings()
    return {
        "llm_model": settings.llm_model,
        "llm_fallback_model": settings.llm_fallback_model,
        "condense_model": settings.condense_model if settings.condense_enabled else None,
        "embedding_model": settings.embedding_model,
        "rerank_enabled": settings.rerank_enabled,
        "rerank_model": settings.rerank_model if settings.rerank_enabled else None,
        "history_window_n": settings.history_window_n,
        "top_k": settings.top_k,
        "rerank_top_k": settings.rerank_top_k,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
