"""CLI entrypoint: `python -m src.ingestion [--recreate]`.

Loads clean documents, chunks them, embeds the chunks and indexes
everything in Qdrant (FR3).
"""

import argparse
import json
import logging
from pathlib import Path

from src.config import get_settings
from src.ingestion.chunker import chunk_document
from src.ingestion.embedder import EmbeddingService
from src.models import Document
from src.repositories.vector_repository import VectorRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_documents(clean_dir: str) -> list[Document]:
    docs = []
    for path in sorted(Path(clean_dir).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        docs.append(Document(**data))
    return docs


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Chunk, embed and index clean documents")
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate the collection")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    docs = load_documents(settings.clean_dir)
    if not docs:
        logger.error("No clean documents in %s — run `python -m src.scraper` first", settings.clean_dir)
        raise SystemExit(1)

    chunks = []
    for doc in docs:
        chunks.extend(chunk_document(doc, settings.chunk_size, settings.chunk_overlap))
    logger.info("Chunked %d documents into %d chunks", len(docs), len(chunks))

    embedder = EmbeddingService(settings.embedding_model)
    repo = VectorRepository(settings.qdrant_url, settings.qdrant_collection)
    repo.ensure_collection(vector_size=embedder.dimension, recreate=args.recreate)

    for start in range(0, len(chunks), args.batch_size):
        batch = chunks[start : start + args.batch_size]
        vectors = embedder.embed_passages([c.text for c in batch])
        repo.upsert_chunks(batch, vectors)
        logger.info("Indexed %d/%d chunks", min(start + args.batch_size, len(chunks)), len(chunks))

    logger.info("Done — collection '%s' now holds %d points", settings.qdrant_collection, repo.count())


if __name__ == "__main__":
    main()
