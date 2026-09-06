"""
Text chunker — splits raw documents into overlapping chunks
suitable for embedding and retrieval.

Strategy:
  - Complaints: Semantic split at sentence boundaries
  - Policy PDFs: Recursive character split (respects paragraphs)
  - FAQ / short text: Passed through as-is if under chunk_size
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.sources.base import RawDocument

logger = get_logger(__name__)


class DocumentChunker:
    """
    Splits RawDocuments into smaller chunks with metadata propagation.

    Each input RawDocument → N output RawDocuments (chunks).
    Chunk size and overlap are read from global settings.
    """

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            # Split on: double newlines → newlines → sentences → words → chars
            separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
            length_function=len,
            is_separator_regex=False,
        )

    def chunk(self, doc: RawDocument) -> list[RawDocument]:
        """
        Split a single RawDocument into chunks.
        Returns the original document unchanged if it's already small enough.
        """
        text = doc.text.strip()

        # Skip empty documents
        if not text:
            return []

        # If text is already within chunk_size, return as-is
        if len(text) <= self.chunk_size:
            return [doc]

        splits = self._splitter.split_text(text)
        chunks: list[RawDocument] = []

        for i, chunk_text in enumerate(splits):
            chunk_text = chunk_text.strip()
            if len(chunk_text) < 30:  # Skip trivially short chunks
                continue

            # Propagate parent metadata + add chunk position info
            chunk_metadata = {
                **doc.metadata,
                "chunk_index": i,
                "chunk_count": len(splits),
                "chunk_size": len(chunk_text),
            }
            chunks.append(RawDocument(text=chunk_text, metadata=chunk_metadata))

        return chunks

    def chunk_batch(self, docs: list[RawDocument]) -> list[RawDocument]:
        """Chunk a batch of documents, flattening the result."""
        all_chunks: list[RawDocument] = []
        for doc in docs:
            all_chunks.extend(self.chunk(doc))
        logger.debug(
            "Chunked batch",
            input_docs=len(docs),
            output_chunks=len(all_chunks),
        )
        return all_chunks
