"""
SEC EDGAR ingestion source.

Fetches public company 10-K annual filings via the free EDGAR API.
No API key required — public domain data.

API docs: https://efts.sec.gov/LATEST/search-index?q=%22annual+report%22&dateRange=custom
Full-text search: https://efts.sec.gov/LATEST/search-index
"""
import time
from pathlib import Path
from typing import Iterator

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.sources.base import BaseSource, RawDocument

logger = get_logger(__name__)

# Major US financial companies — their 10-Ks are the knowledge base
# for answering questions like "what are JPMorgan's risk factors?"
DEFAULT_COMPANIES = [
    # (company_name, CIK)
    ("JPMorgan Chase", "0000019617"),
    ("Bank of America", "0000070858"),
    ("Wells Fargo", "0000072971"),
    ("Citigroup", "0000831001"),
    ("Goldman Sachs", "0000886982"),
    ("Morgan Stanley", "0000895421"),
    ("American Express", "0000004962"),
    ("Capital One", "0000927628"),
    ("Discover Financial", "0001393612"),
    ("Ally Financial", "0000040729"),
]

EDGAR_BASE = settings.sec_edgar_base_url
HEADERS = {
    # EDGAR requires a User-Agent with contact info per their policy
    "User-Agent": "fin-ai-agent research@example.com",
    "Accept": "application/json",
}


class SECEdgarSource(BaseSource):
    """
    Fetches 10-K filings from SEC EDGAR for target financial companies.

    Each filing section (Risk Factors, MD&A, Business Overview) becomes
    a separate RawDocument for fine-grained retrieval.
    """

    source_name = "sec_edgar"
    collection = settings.qdrant_collection_policies

    def __init__(
        self,
        raw_data_dir: Path = Path("data/raw/sec"),
        companies: list[tuple[str, str]] | None = None,
        max_filings_per_company: int = 2,
    ) -> None:
        self.raw_data_dir = raw_data_dir
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.companies = companies or DEFAULT_COMPANIES
        self.max_filings_per_company = max_filings_per_company
        self._client = httpx.Client(
            headers=HEADERS,
            timeout=30,
            follow_redirects=True,
        )

    # ── EDGAR API Helpers ─────────────────────────────────────────────────────

    def _get_company_filings(self, cik: str) -> list[dict]:
        """Return list of 10-K filing metadata for a CIK."""
        # Pad CIK to 10 digits as EDGAR requires
        padded_cik = cik.zfill(10)
        url = f"{EDGAR_BASE}/submissions/CIK{padded_cik}.json"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch EDGAR filings", cik=cik, error=str(exc))
            return []

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        accessions = filings.get("accessionNumber", [])
        dates = filings.get("filingDate", [])

        # Filter to 10-K only
        results = []
        for form, acc, date in zip(forms, accessions, dates):
            if form == "10-K":
                results.append({"accession": acc, "date": date, "cik": padded_cik})
            if len(results) >= self.max_filings_per_company:
                break

        return results

    def _get_filing_text(self, cik: str, accession: str) -> str | None:
        """
        Download the primary 10-K document text from EDGAR.

        EDGAR filing index URL format (correct):
          https://www.sec.gov/Archives/edgar/data/<CIK_no_leading_zeros>/<acc_no_dashes>/<acc_with_dashes>-index.htm
        The JSON index endpoint:
          https://data.sec.gov/submissions/CIK<padded>.json  ← used in _get_company_filings
        The actual filing document URL is assembled from the accession number directly.
        """
        acc_clean = accession.replace("-", "")
        # CIK must NOT have leading zeros for the Archives path
        cik_int = str(int(cik))

        # EDGAR filing index — returns HTML, but the primary doc URL is predictable
        # The primary 10-K document is always at:
        #   /Archives/edgar/data/<cik>/<acc_clean>/<acc_with_dashes>.htm  (newer filings)
        # We also try the index JSON via EDGAR's EFTS endpoint
        index_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/"
            f"{accession}-index.json"
        )
        try:
            resp = self._client.get(index_url)
            resp.raise_for_status()
            index_data = resp.json()
        except Exception:
            # Fallback: try the standard .htm index page and scrape the document list
            index_data = {}

        # Look for the primary 10-K document in the index
        for doc in index_data.get("documents", []):
            doc_type = doc.get("type", "")
            doc_url_path = doc.get("url", "") or doc.get("documentUrl", "")
            if doc_type == "10-K" and doc_url_path:
                # Ensure absolute URL
                if doc_url_path.startswith("/"):
                    doc_url = f"https://www.sec.gov{doc_url_path}"
                else:
                    doc_url = doc_url_path
                try:
                    time.sleep(0.12)  # Respect EDGAR rate limit (~10 req/s)
                    doc_resp = self._client.get(doc_url)
                    doc_resp.raise_for_status()
                    return doc_resp.text
                except Exception as exc:
                    logger.warning("Failed to fetch filing document", url=doc_url, error=str(exc))
                    return None

        # Last resort: try the predictable primary document URL
        # EDGAR naming convention: accession number with dashes + .htm
        primary_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{accession}.htm"
        )
        try:
            time.sleep(0.12)
            resp = self._client.get(primary_url)
            resp.raise_for_status()
            logger.debug("Used fallback primary URL", url=primary_url)
            return resp.text
        except Exception as exc:
            logger.warning(
                "All filing fetch attempts failed",
                accession=accession,
                cik=cik_int,
                error=str(exc),
            )
            return None

    def _clean_html(self, html: str) -> str:
        """Strip HTML tags and normalise whitespace from an EDGAR filing."""
        import re
        # Remove script and style blocks entirely
        html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove all remaining tags
        html = re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        html = re.sub(r"[ \t]+", " ", html)
        html = re.sub(r"\n{3,}", "\n\n", html)
        return html.strip()

    def _extract_sections(self, raw_text: str, company: str, date: str) -> list[RawDocument]:
        """
        Split the raw 10-K text into named sections for targeted retrieval.
        Cleans HTML first, then uses heuristic section detection.
        """
        documents = []
        # Clean HTML before section parsing
        clean_text = self._clean_html(raw_text)
        # Key 10-K sections we care about for the complaint agent
        section_markers = {
            "Risk Factors": ["item 1a", "risk factors"],
            "Business Overview": ["item 1.", "business\n", "item 1 business"],
            "Legal Proceedings": ["item 3", "legal proceedings"],
            "MD&A": ["item 7", "management", "discussion and analysis"],
            "Quantitative Risk": ["item 7a", "quantitative and qualitative"],
        }

        text_lower = clean_text.lower()

        for section_name, markers in section_markers.items():
            for marker in markers:
                idx = text_lower.find(marker)
                if idx != -1:
                    section_text = clean_text[idx : idx + 3000].strip()
                    if len(section_text) > 200:
                        documents.append(
                            RawDocument(
                                text=section_text,
                                metadata={
                                    "source": "sec_edgar",
                                    "company": company,
                                    "section": section_name,
                                    "filing_date": date,
                                    "filing_type": "10-K",
                                    "collection": self.collection,
                                },
                            )
                        )
                        break

        return documents

    # ── Public API ────────────────────────────────────────────────────────────

    def iter_documents(self) -> Iterator[RawDocument]:
        """Yield 10-K section documents for all configured companies."""
        total = 0
        for company_name, cik in self.companies:
            logger.info("Fetching SEC filings", company=company_name, cik=cik)
            filings = self._get_company_filings(cik)

            for filing in filings:
                time.sleep(0.15)  # Respect EDGAR rate limiting
                raw_text = self._get_filing_text(filing["cik"], filing["accession"])
                if not raw_text:
                    continue

                sections = self._extract_sections(
                    raw_text, company_name, filing["date"]
                )
                for doc in sections:
                    yield doc
                    total += 1

                logger.info(
                    "Filing processed",
                    company=company_name,
                    date=filing["date"],
                    sections=len(sections),
                )

        logger.info("SEC EDGAR ingestion complete", total_documents=total)

    def __del__(self) -> None:
        self._client.close()
