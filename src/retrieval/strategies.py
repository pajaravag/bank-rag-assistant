"""Retrieval strategies (Strategy pattern).

The chat service depends on the `RetrievalStrategy` interface only;
which concrete strategy runs is decided by configuration at startup
(`build_retrieval_strategy`), not by if-branches in business logic.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod

from src.config import Settings
from src.ingestion.embedder import EmbeddingService
from src.models import RetrievedChunk
from src.repositories.vector_repository import VectorRepository
from src.retrieval.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)


class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve(self, query: str) -> list[RetrievedChunk]:
        """Returns the chunks most relevant to `query`, best first."""


class SimilaritySearch(RetrievalStrategy):
    """Plain bi-encoder cosine similarity against the vector store."""

    def __init__(self, embedder: EmbeddingService, repo: VectorRepository, top_k: int) -> None:
        self.embedder = embedder
        self.repo = repo
        self.top_k = top_k

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        return self.repo.search(self.embedder.embed_query(query), self.top_k)


class RerankedSearch(RetrievalStrategy):
    """Wraps a base strategy: dedupes candidates, then cross-encoder reranks."""

    def __init__(self, base: RetrievalStrategy, reranker: CrossEncoderReranker, final_k: int) -> None:
        self.base = base
        self.reranker = reranker
        self.final_k = final_k

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        candidates = _dedupe(self.base.retrieve(query))
        return self.reranker.rerank(query, candidates)[: self.final_k]


def _dedupe(candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Drop near-duplicate chunks (repeated page blocks, carousels)."""
    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for c in candidates:
        key = hashlib.sha1(" ".join(c.chunk.text.lower().split()).encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def build_retrieval_strategy(
    settings: Settings, embedder: EmbeddingService, repo: VectorRepository
) -> RetrievalStrategy:
    base = SimilaritySearch(embedder, repo, settings.top_k)
    if not settings.rerank_enabled:
        logger.info("Retrieval strategy: similarity search (top_k=%d)", settings.top_k)
        return base
    logger.info(
        "Retrieval strategy: similarity (top_k=%d) + rerank (final_k=%d)",
        settings.top_k,
        settings.rerank_top_k,
    )
    return RerankedSearch(base, CrossEncoderReranker(settings.rerank_model), settings.rerank_top_k)
