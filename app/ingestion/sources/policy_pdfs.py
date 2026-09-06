"""
Policy PDF ingestion source.

Ingests regulatory documents from:
  - FDIC interagency statements and rules
  - CFPB policy documents and rule PDFs
  - Any locally placed PDFs in data/policies/

All sources are public domain / freely available.
"""
from pathlib import Path
from typing import Iterator

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.sources.base import BaseSource, RawDocument

logger = get_logger(__name__)

# Public regulatory PDFs — free, no auth required
PUBLIC_POLICY_PDFS = [
    # CFPB
    {
        "name": "CFPB Consumer Response Annual Report 2024",
        "url": "https://files.consumerfinance.gov/f/documents/cfpb_cr-annual-report_2025-05.pdf",
        "category": "consumer_protection",
        "issuer": "CFPB",
    },
    {
        "name": "CFPB Supervisory Highlights",
        "url": "https://files.consumerfinance.gov/f/documents/cfpb_supervisory-highlights_issue-34_2024-06.pdf",
        "category": "compliance",
        "issuer": "CFPB",
    },
    # FDIC
    {
        "name": "FDIC Applications Procedures Manual",
        "url": "https://fdic.gov/system/files/2024-07/section-01-04-publicinfo.pdf",
        "category": "banking_regulation",
        "issuer": "FDIC",
    },
]


class PolicyPDFSource(BaseSource):
    """
    Downloads public regulatory PDFs and extracts text page-by-page.

    Also picks up any manually placed PDFs in data/policies/.
    Each page becomes a RawDocument with section metadata.
    """

    source_name = "policy_pdfs"
    collection = settings.qdrant_collection_policies

    def __init__(
        self,
        raw_data_dir: Path = Path("data/policies"),
        policy_list: list[dict] | None = None,
    ) -> None:
        self.raw_data_dir = raw_data_dir
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.policy_list = policy_list or PUBLIC_POLICY_PDFS

    def _download_pdf(self, url: str, dest: Path) -> bool:
        """Download a PDF to dest. Returns True on success."""
        if dest.exists():
            logger.info("PDF already cached", path=str(dest))
            return True
        try:
            logger.info("Downloading policy PDF", url=url)
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
            dest.write_bytes(resp.content)
            logger.info("PDF saved", path=str(dest), size_kb=len(resp.content) // 1024)
            return True
        except Exception as exc:
            logger.warning("Failed to download PDF", url=url, error=str(exc))
            return False

    def _extract_text_from_pdf(self, pdf_path: Path) -> list[tuple[int, str]]:
        """
        Extract (page_number, text) pairs from a PDF.
        Uses pypdf — install with: pip install pypdf
        """
        try:
            from pypdf import PdfReader  # type: ignore[import]
        except ImportError:
            logger.error("pypdf not installed. Run: pip install pypdf")
            return []

        pages: list[tuple[int, str]] = []
        try:
            reader = PdfReader(str(pdf_path))
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                text = text.strip()
                if len(text) > 100:  # Skip nearly empty pages
                    pages.append((i + 1, text))
        except Exception as exc:
            logger.warning("Failed to parse PDF", path=str(pdf_path), error=str(exc))

        return pages

    def iter_documents(self) -> Iterator[RawDocument]:
        """
        Yields one RawDocument per page for all policy PDFs.
        Covers both downloaded remote PDFs and locally placed PDFs.
        """
        total = 0

        # ── Remote PDFs ──────────────────────────────────────────────────────
        for policy in self.policy_list:
            filename = policy["url"].split("/")[-1].split("?")[0]
            dest = self.raw_data_dir / filename

            if not self._download_pdf(policy["url"], dest):
                continue

            pages = self._extract_text_from_pdf(dest)
            for page_num, text in pages:
                yield RawDocument(
                    text=text,
                    metadata={
                        "source": "policy_pdf",
                        "document_name": policy["name"],
                        "issuer": policy["issuer"],
                        "category": policy["category"],
                        "page": page_num,
                        "filename": filename,
                        "collection": self.collection,
                    },
                )
                total += 1

        # ── Locally placed PDFs (data/policies/*.pdf) ─────────────────────────
        for pdf_path in self.raw_data_dir.glob("*.pdf"):
            pages = self._extract_text_from_pdf(pdf_path)
            for page_num, text in pages:
                yield RawDocument(
                    text=text,
                    metadata={
                        "source": "policy_pdf_local",
                        "document_name": pdf_path.stem.replace("_", " ").title(),
                        "issuer": "Unknown",
                        "category": "general",
                        "page": page_num,
                        "filename": pdf_path.name,
                        "collection": self.collection,
                    },
                )
                total += 1

        logger.info("Policy PDF ingestion complete", total_documents=total)
