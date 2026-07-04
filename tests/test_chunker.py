from src.ingestion.chunker import chunk_document
from src.models import Document


def make_doc(text: str) -> Document:
    return Document(url="https://x.co/p", title="T", text=text, fetched_at="2026-07-04T00:00:00")


def test_short_document_yields_single_chunk():
    chunks = chunk_document(make_doc("Hola mundo.\nSegunda línea."), chunk_size=800, chunk_overlap=100)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert "Hola mundo." in chunks[0].text


def test_chunks_respect_size_limit():
    text = "\n".join(f"Párrafo número {i} con contenido suficiente para ocupar espacio." for i in range(50))
    chunks = chunk_document(make_doc(text), chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 1
    # Allow slack for the overlap prefix carried into each chunk
    assert all(len(c.text) <= 300 + 50 + 1 for c in chunks)


def test_long_paragraph_split_on_sentences():
    text = "Esta es una frase. " * 100  # single paragraph, ~1900 chars
    chunks = chunk_document(make_doc(text.strip()), chunk_size=400, chunk_overlap=0)
    assert len(chunks) > 1
    assert all(len(c.text) <= 401 for c in chunks)


def test_chunk_indices_are_sequential():
    text = "\n".join(f"Contenido del párrafo {i} " * 10 for i in range(20))
    chunks = chunk_document(make_doc(text), chunk_size=300, chunk_overlap=40)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_empty_document_yields_no_chunks():
    assert chunk_document(make_doc(""), chunk_size=800, chunk_overlap=100) == []
