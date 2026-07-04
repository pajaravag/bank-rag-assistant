"""Cross-encoder reranking: scores (query, passage) pairs jointly.

Slower than bi-encoder similarity but far more precise — used to
reorder the candidate set before it reaches the LLM (bonus B1).
"""

from __future__ import annotations

import logging

from sentence_transformers import CrossEncoder

from src.models import RetrievedChunk

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        logger.info("Loading reranker model %s", model_name)
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return []
        scores = self.model.predict([(query, c.chunk.text) for c in candidates])
        rescored = [
            RetrievedChunk(chunk=c.chunk, score=float(score))
            for c, score in zip(candidates, scores)
        ]
        return sorted(rescored, key=lambda r: r.score, reverse=True)
