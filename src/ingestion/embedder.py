"""Embedding service wrapping sentence-transformers.

The e5 model family requires asymmetric prefixes: documents are encoded
as "passage: ..." and queries as "query: ..." — omitting them degrades
retrieval quality significantly.
"""

from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str) -> None:
        logger.info("Loading embedding model %s", model_name)
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self._is_e5 = "e5" in model_name.lower()

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def embed_passages(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        prefixed = [f"passage: {t}" for t in texts] if self._is_e5 else texts
        vectors = self.model.encode(prefixed, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        prefixed = f"query: {text}" if self._is_e5 else text
        return self.model.encode([prefixed], normalize_embeddings=True)[0].tolist()
