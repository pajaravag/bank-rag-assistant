"""Paragraph-aware text chunking.

Packs whole paragraphs into chunks up to `chunk_size` characters; a
paragraph longer than the limit is split on sentence-ish boundaries.
Consecutive chunks share `chunk_overlap` characters of context.
"""

from __future__ import annotations

from src.models import Chunk, Document


def _split_long_paragraph(paragraph: str, chunk_size: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for sentence in paragraph.replace("? ", "?\x00").replace("! ", "!\x00").replace(". ", ".\x00").split("\x00"):
        if current and len(current) + len(sentence) + 1 > chunk_size:
            pieces.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current.strip():
        pieces.append(current.strip())
    return pieces


def chunk_document(doc: Document, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    paragraphs: list[str] = []
    for para in doc.text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) > chunk_size:
            paragraphs.extend(_split_long_paragraph(para, chunk_size))
        else:
            paragraphs.append(para)

    chunks: list[Chunk] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 1 > chunk_size:
            chunks.append(_make_chunk(doc, current, len(chunks)))
            # Carry the tail of the previous chunk as overlap context
            current = current[-chunk_overlap:] + "\n" + para if chunk_overlap else para
        else:
            current = f"{current}\n{para}" if current else para
    if current.strip():
        chunks.append(_make_chunk(doc, current, len(chunks)))
    return chunks


def _make_chunk(doc: Document, text: str, index: int) -> Chunk:
    return Chunk(url=doc.url, title=doc.title, text=text.strip(), chunk_index=index)
