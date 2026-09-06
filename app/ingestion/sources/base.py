"""
Base class and shared types for all ingestion sources.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class RawDocument:
    """A single raw document before chunking and embedding."""
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseSource(ABC):
    """Abstract base for all data sources (CFPB, SEC, Policy PDFs, etc.)."""

    source_name: str = "base"
    collection: str = ""

    @abstractmethod
    def iter_documents(self) -> Iterator[RawDocument]:
        """Yield raw documents from this source."""
        ...
