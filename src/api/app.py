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
    conversations = ConversationRepository(settings.history_db_path)
    state["chat_service"] = ChatService(
        retrieval=build_retrieval_strategy(
            settings,
            EmbeddingService(settings.embedding_model),
            VectorRepository(settings.qdrant_url, settings.qdrant_collection),
        ),
        llm=LLMProviderFactory.create(settings),
        conversations=conversations,
        history_window_n=settings.history_window_n,
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
