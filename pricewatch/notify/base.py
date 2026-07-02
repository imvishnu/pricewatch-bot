"""Notifier abstraction — any alert channel implements this."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    @abstractmethod
    async def send(self, recipient: str, text: str) -> bool:
        """Send `text` to `recipient` (channel-specific id). Returns success."""
        raise NotImplementedError
