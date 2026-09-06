"""
CFPB Consumer Complaint Database ingestion source.

Downloads the public complaint CSV from:
  https://files.consumerfinance.gov/ccdb/complaints.csv.zip

Free, no API key required. Updated weekly by CFPB.
~7.8M complaints across mortgages, credit cards, loans, banking.
"""
import io
import zipfile
from pathlib import Path
from typing import Iterator

import httpx
import pandas as pd

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.sources.base import BaseSource, RawDocument

logger = get_logger(__name__)

# Columns we actually need for RAG — drop the rest to save memory
USEFUL_COLUMNS = [
    "Complaint ID",
    "Date received",
    "Product",
    "Sub-product",
    "Issue",
    "Sub-issue",
    "Consumer complaint narrative",
    "Company public response",
    "Company",
    "State",
    "Tags",
]

# Only products relevant to our use case
TARGET_PRODUCTS = [
    "Mortgage",
    "Credit card",
    "Checking or savings account",
    "Student loan",
    "Personal loan",
    "Payday loan",
    "Debt collection",
    "Credit reporting",
    "Money transfer",
    "Vehicle loan or lease",
]


class CFPBSource(BaseSource):
    """
    Streams the CFPB complaint CSV and yields RawDocuments.

    Each complaint with a consumer narrative becomes one document.
    The company response (when available) is appended as resolution context.
    """

    source_name = "cfpb_complaints"
    collection = settings.qdrant_collection_complaints

    def __init__(
        self,
        raw_data_dir: Path = Path("data/raw"),
        max_records: int | None = None,
        sample_mode: bool = False,
    ) -> None:
        self.raw_data_dir = raw_data_dir
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = raw_data_dir / "cfpb_complaints.csv"
        # In sample_mode pull only first 5K rows — useful for dev iteration
        self.max_records = 5_000 if sample_mode else max_records

    # ── Download ─────────────────────────────────────────────────────────────

    def download(self, force: bool = False) -> Path:
        """Download and unzip the CFPB CSV. Skips if already present."""
        if self.csv_path.exists() and not force:
            logger.info("CFPB CSV already exists, skipping download", path=str(self.csv_path))
            return self.csv_path

        logger.info("Downloading CFPB complaint database", url=settings.cfpb_data_url)
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            response = client.get(settings.cfpb_data_url)
            response.raise_for_status()

        logger.info("Unzipping CFPB data", size_mb=round(len(response.content) / 1e6, 1))
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # The zip contains a single CSV
            csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
            zf.extract(csv_name, self.raw_data_dir)
            extracted = self.raw_data_dir / csv_name
            # Only rename if not already at target path
            if extracted != self.csv_path:
                if self.csv_path.exists():
                    self.csv_path.unlink()  # Remove old file first
                extracted.rename(self.csv_path)

        logger.info("CFPB CSV saved", path=str(self.csv_path))
        return self.csv_path

    # ── Parse ─────────────────────────────────────────────────────────────────

    def iter_documents(self) -> Iterator[RawDocument]:
        """
        Yields one RawDocument per complaint that has a consumer narrative.
        Text format:
            COMPLAINT: <narrative>
            RESOLUTION: <company public response>
        """
        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"CFPB CSV not found at {self.csv_path}. Run download() first."
            )

        logger.info("Parsing CFPB complaints", path=str(self.csv_path))
        chunks = pd.read_csv(
            self.csv_path,
            usecols=[c for c in USEFUL_COLUMNS if c != "Consumer complaint narrative"],
            # Narrative needs dtype=str explicitly to avoid mixed-type warnings
            dtype={"Consumer complaint narrative": str, "Complaint ID": str},
            chunksize=10_000,
            on_bad_lines="skip",
            low_memory=False,
        )

        # Re-read with narrative column included
        chunks = pd.read_csv(
            self.csv_path,
            usecols=USEFUL_COLUMNS,
            dtype=str,
            chunksize=10_000,
            on_bad_lines="skip",
            low_memory=False,
        )

        yielded = 0
        for chunk in chunks:
            # Filter: must have narrative text
            chunk = chunk[chunk["Consumer complaint narrative"].notna()].copy()

            # Filter: target products only
            chunk = chunk[chunk["Product"].isin(TARGET_PRODUCTS)]

            for _, row in chunk.iterrows():
                narrative = str(row.get("Consumer complaint narrative", "")).strip()
                if len(narrative) < 50:
                    continue

                resolution = str(row.get("Company public response", "")).strip()
                text = f"COMPLAINT: {narrative}"
                if resolution and resolution.lower() not in ("nan", "none", ""):
                    text += f"\n\nRESOLUTION: {resolution}"

                yield RawDocument(
                    text=text,
                    metadata={
                        "source": "cfpb",
                        "complaint_id": str(row.get("Complaint ID", "")),
                        "product": str(row.get("Product", "")),
                        "sub_product": str(row.get("Sub-product", "")),
                        "issue": str(row.get("Issue", "")),
                        "sub_issue": str(row.get("Sub-issue", "")),
                        "company": str(row.get("Company", "")),
                        "state": str(row.get("State", "")),
                        "date_received": str(row.get("Date received", "")),
                        "tags": str(row.get("Tags", "")),
                        "collection": self.collection,
                    },
                )

                yielded += 1
                if self.max_records and yielded >= self.max_records:
                    logger.info("Reached max_records limit", count=yielded)
                    return

        logger.info("CFPB parsing complete", total_documents=yielded)
