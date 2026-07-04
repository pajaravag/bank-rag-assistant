"""Shared data contracts used across scraper, ingestion, retrieval and API."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Document:
    """A cleaned page from the target site."""

    url: str
    title: str
    text: str
    fetched_at: str


@dataclass
class Chunk:
    """A slice of a Document, unit of indexing and retrieval."""

    url: str
    title: str
    text: str
    chunk_index: int


@dataclass
class RetrievedChunk:
    """A chunk returned by the vector store, with its relevance score."""

    chunk: Chunk
    score: float


@dataclass
class ChatTurn:
    """One message in a conversation."""

    role: str  # "user" | "assistant"
    content: str
    sources: list[str] = field(default_factory=list)
