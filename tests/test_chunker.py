"""Unit tests for the document chunker."""
from app.ingestion.processors.chunker import DocumentChunker
from app.ingestion.sources.base import RawDocument


def make_doc(text: str, **meta) -> RawDocument:
    return RawDocument(text=text, metadata={"source": "test", **meta})


def test_short_doc_returned_as_is():
    chunker = DocumentChunker(chunk_size=512, chunk_overlap=64)
    doc = make_doc("This is a short document.")
    result = chunker.chunk(doc)
    assert len(result) == 1
    assert result[0].text == doc.text


def test_long_doc_is_split():
    chunker = DocumentChunker(chunk_size=100, chunk_overlap=10)
    long_text = "word " * 200  # 1000 chars
    doc = make_doc(long_text)
    result = chunker.chunk(doc)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk.text) <= 120  # allow small overshoot at word boundaries


def test_metadata_propagated():
    chunker = DocumentChunker(chunk_size=50, chunk_overlap=5)
    doc = make_doc("a " * 100, product="Mortgage", complaint_id="CPL-001")
    chunks = chunker.chunk(doc)
    for chunk in chunks:
        assert chunk.metadata["product"] == "Mortgage"
        assert chunk.metadata["complaint_id"] == "CPL-001"
        assert "chunk_index" in chunk.metadata


def test_empty_doc_returns_empty():
    chunker = DocumentChunker()
    result = chunker.chunk(make_doc(""))
    assert result == []


def test_chunk_batch():
    chunker = DocumentChunker(chunk_size=100, chunk_overlap=10)
    docs = [make_doc("x " * 100) for _ in range(5)]
    all_chunks = chunker.chunk_batch(docs)
    assert len(all_chunks) > 5  # each doc should produce multiple chunks
