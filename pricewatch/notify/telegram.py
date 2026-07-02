"""Telegram notifier — sends messages via the Bot API."""

from __future__ import annotations

import logging

import httpx

from .base import Notifier

log = logging.getLogger(__name__)


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, client: httpx.AsyncClient | None = None):
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._client = client or httpx.AsyncClient(timeout=15)

    async def send(self, recipient: str, text: str) -> bool:
        """recipient: Telegram chat id (as a string)."""
        try:
            resp = await self._client.post(self._url, json={
                "chat_id": recipient,
                "text": text,
                "disable_web_page_preview": False,
            })
            ok = resp.status_code == 200 and resp.json().get("ok", False)
            if not ok:
                log.warning("Telegram send failed for %s: %s %s",
                            recipient, resp.status_code, resp.text[:200])
            return ok
        except httpx.HTTPError as exc:
            log.warning("Telegram send error for %s: %s", recipient, exc)
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
