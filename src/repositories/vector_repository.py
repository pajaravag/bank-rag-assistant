"""Repository pattern over the vector store (Qdrant).

The rest of the system talks to this interface only; swapping Qdrant
for another engine means reimplementing this one class.
"""

from __future__ import annotations

import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.models import Chunk, RetrievedChunk

logger = logging.getLogger(__name__)


def _point_id(chunk: Chunk) -> str:
    """Deterministic ID so re-ingesting the same page upserts instead of duplicating."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{chunk.url}#{chunk.chunk_index}"))


class VectorRepository:
    def __init__(self, url: str, collection: str) -> None:
        self.client = QdrantClient(url=url)
        self.collection = collection

    def ensure_collection(self, vector_size: int, recreate: bool = False) -> None:
        exists = self.client.collection_exists(self.collection)
        if exists and recreate:
            self.client.delete_collection(self.collection)
            exists = False
        if not exists:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info("Created collection %s (dim=%d)", self.collection, vector_size)

    def upsert_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        points = [
            PointStruct(
                id=_point_id(chunk),
                vector=vector,
                payload={
                    "url": chunk.url,
                    "title": chunk.title,
                    "text": chunk.text,
                    "chunk_index": chunk.chunk_index,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, vector: list[float], top_k: int) -> list[RetrievedChunk]:
        hits = self.client.query_points(
            collection_name=self.collection, query=vector, limit=top_k, with_payload=True
        ).points
        return [
            RetrievedChunk(
                chunk=Chunk(
                    url=hit.payload["url"],
                    title=hit.payload["title"],
                    text=hit.payload["text"],
                    chunk_index=hit.payload["chunk_index"],
                ),
                score=hit.score,
            )
            for hit in hits
        ]

    def count(self) -> int:
        return self.client.count(self.collection).count
