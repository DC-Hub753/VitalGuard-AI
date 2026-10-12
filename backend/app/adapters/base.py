"""Base source adapter interface for observation ingestion."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..observation_contract import CanonicalObservation


class BaseSourceAdapter(ABC):
    """Abstract base adapter converting source-specific payloads to canonical observations."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the source system or device feed."""
        ...

    @property
    @abstractmethod
    def source_mode(self) -> str:
        """Source mode: 'historical_replay', 'synthetic_demo', or 'authorized_feed'."""
        ...

    @abstractmethod
    def transform(self, raw_data: dict[str, Any]) -> CanonicalObservation:
        """Transform provider payload to CanonicalObservation. Raises ValueError on schema violation."""
        ...
