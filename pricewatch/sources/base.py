"""PriceSource abstraction.

Any price backend (Creators API, a scraper, ...) implements `PriceSource`.
The poller and bot depend only on this interface, so a scraper source can
be dropped in later without touching anything else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class PriceResult:
    asin: str
    price: float
    currency: str
    title: str
    category: str


class PriceSource(ABC):
    @abstractmethod
    async def fetch(self, asin: str) -> PriceResult:
        """Fetch the current price/metadata for an ASIN.

        Raises an exception on failure (network error, item unavailable);
        the poller logs and skips that product for the run.
        """
        raise NotImplementedError

    def product_link(self, asin: str) -> str:
        """Link to include in alerts. Sources may add affiliate tags."""
        return f"https://www.amazon.in/dp/{asin}"
