"""
Main ingestion pipeline — orchestrates download → chunk → embed → index.

Run via CLI:
  python -m app.ingestion.pipeline --all
  python -m app.ingestion.pipeline --source cfpb
  python -m app.ingestion.pipeline --source sec
  python -m app.ingestion.pipeline --source policy

Architecture:
  Source → Chunker → Embedder → VectorStoreWriter

  Each source streams documents to avoid loading everything into memory.
  Chunks are accumulated into embed-batches, then upserted.
"""
import argparse
import time
from pathlib import Path
from typing import Iterator

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.ingestion.processors.chunker import DocumentChunker
from app.ingestion.processors.embedder import Embedder
from app.ingestion.processors.vector_store import VectorStoreWriter
from app.ingestion.sources.base import RawDocument
from app.ingestion.sources.cfpb import CFPBSource
from app.ingestion.sources.policy_pdfs import PolicyPDFSource
from app.ingestion.sources.sec_edgar import SECEdgarSource

logger = get_logger(__name__)

# How many chunks to accumulate before sending to embedder + vector store
EMBED_BATCH_SIZE = 64


class IngestionPipeline:
    """
    End-to-end ingestion orchestrator.

    Usage:
        pipeline = IngestionPipeline()
        pipeline.run_cfpb(sample_mode=True)   # dev/testing
        pipeline.run_sec()
        pipeline.run_policy()
        pipeline.run_all()
    """

    def __init__(self, embedding_provider: str = "openai") -> None:
        self.chunker = DocumentChunker()
        self.embedder = Embedder(provider=embedding_provider)  # type: ignore[arg-type]
        self.writer = VectorStoreWriter(embedding_provider=embedding_provider)

    # ── Core processing loop ─────────────────────────────────────────────────

    def _process_stream(
        self,
        doc_stream: Iterator[RawDocument],
        collection: str,
        source_name: str,
    ) -> dict[str, int]:
        """
        Process a stream of RawDocuments end-to-end.
        Returns stats dict.
        """
        stats = {"raw_docs": 0, "chunks": 0, "embedded": 0, "upserted": 0}
        pending_chunks: list[RawDocument] = []

        def flush_batch(chunks: list[RawDocument]) -> int:
            if not chunks:
                return 0
            doc_vecs = self.embedder.embed_documents(chunks)
            n = self.writer.upsert(collection, doc_vecs)
            return n

        start = time.time()

        for raw_doc in doc_stream:
            stats["raw_docs"] += 1
            chunks = self.chunker.chunk(raw_doc)
            stats["chunks"] += len(chunks)
            pending_chunks.extend(chunks)

            # Flush when we have a full embed batch
            if len(pending_chunks) >= EMBED_BATCH_SIZE:
                n = flush_batch(pending_chunks)
                stats["upserted"] += n
                pending_chunks = []

            # Progress log every 500 raw docs
            if stats["raw_docs"] % 500 == 0:
                elapsed = time.time() - start
                logger.info(
                    "Ingestion progress",
                    source=source_name,
                    raw_docs=stats["raw_docs"],
                    chunks=stats["chunks"],
                    upserted=stats["upserted"],
                    elapsed_s=round(elapsed, 1),
                )

        # Flush remaining
        if pending_chunks:
            n = flush_batch(pending_chunks)
            stats["upserted"] += n

        elapsed = time.time() - start
        logger.info(
            "Ingestion complete",
            source=source_name,
            collection=collection,
            **stats,
            elapsed_s=round(elapsed, 1),
        )
        return stats

    # ── Public run methods ───────────────────────────────────────────────────

    def run_cfpb(self, sample_mode: bool = False, force_download: bool = False) -> dict:
        """
        Ingest CFPB Consumer Complaint Database.

        sample_mode=True → only ingest 5K complaints (fast dev iteration).
        """
        logger.info("Starting CFPB ingestion", sample_mode=sample_mode)
        source = CFPBSource(sample_mode=sample_mode)
        source.download(force=force_download)
        return self._process_stream(
            source.iter_documents(),
            collection=settings.qdrant_collection_complaints,
            source_name="cfpb",
        )

    def run_sec(self, max_filings_per_company: int = 2) -> dict:
        """
        Ingest SEC EDGAR 10-K filings for major US financial companies.
        """
        logger.info("Starting SEC EDGAR ingestion")
        source = SECEdgarSource(max_filings_per_company=max_filings_per_company)
        return self._process_stream(
            source.iter_documents(),
            collection=settings.qdrant_collection_policies,
            source_name="sec_edgar",
        )

    def run_policy(self) -> dict:
        """
        Ingest FDIC/CFPB regulatory policy PDFs.
        """
        logger.info("Starting policy PDF ingestion")
        source = PolicyPDFSource()
        return self._process_stream(
            source.iter_documents(),
            collection=settings.qdrant_collection_policies,
            source_name="policy_pdfs",
        )

    def run_all(self, sample_cfpb: bool = False) -> dict[str, dict]:
        """Run all sources sequentially."""
        logger.info("Starting full ingestion pipeline")
        results = {
            "cfpb": self.run_cfpb(sample_mode=sample_cfpb),
            "sec": self.run_sec(),
            "policy": self.run_policy(),
        }
        total_upserted = sum(r["upserted"] for r in results.values())
        logger.info("Full pipeline complete", total_vectors=total_upserted)
        return results

    def status(self) -> dict[str, int]:
        """Return current vector count per collection."""
        return {
            "complaints": self.writer.collection_count(settings.qdrant_collection_complaints),
            "policies": self.writer.collection_count(settings.qdrant_collection_policies),
            "faq": self.writer.collection_count(settings.qdrant_collection_faq),
        }


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Fin AI Agent — Data Ingestion Pipeline")
    parser.add_argument(
        "--source",
        choices=["cfpb", "sec", "policy", "all"],
        default="all",
        help="Which data source to ingest",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use sample mode for CFPB (5K records, faster)",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "local"],
        default="openai",
        help="Embedding provider to use",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current vector store counts and exit",
    )
    args = parser.parse_args()

    pipeline = IngestionPipeline(embedding_provider=args.provider)

    if args.status:
        counts = pipeline.status()
        for name, count in counts.items():
            print(f"  {name:20s}: {count:,} vectors")
        return

    source_map = {
        "cfpb": lambda: pipeline.run_cfpb(sample_mode=args.sample),
        "sec": pipeline.run_sec,
        "policy": pipeline.run_policy,
        "all": lambda: pipeline.run_all(sample_cfpb=args.sample),
    }
    source_map[args.source]()


if __name__ == "__main__":
    main()
