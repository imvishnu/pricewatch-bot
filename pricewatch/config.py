"""Configuration loaded from environment variables.

All secrets come from the environment (see .env.example). Nothing is
hard-coded here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str:
    return os.environ.get(name, "").strip()


@dataclass(frozen=True)
class Config:
    database_url: str
    telegram_bot_token: str
    price_source: str  # "scraper" (default) or "creators"
    creators_client_id: str
    creators_client_secret: str
    partner_tag: str

    @classmethod
    def from_env(cls) -> "Config":
        price_source = os.environ.get("PRICE_SOURCE", "scraper").strip().lower()
        if price_source not in ("scraper", "creators"):
            raise ConfigError(f"PRICE_SOURCE must be 'scraper' or 'creators', "
                              f"got {price_source!r}")
        cfg = cls(
            database_url=_require("DATABASE_URL"),
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            price_source=price_source,
            # Only required when PRICE_SOURCE=creators
            creators_client_id=_optional("CREATORS_CLIENT_ID"),
            creators_client_secret=_optional("CREATORS_CLIENT_SECRET"),
            partner_tag=_optional("PARTNER_TAG"),
        )
        if price_source == "creators":
            for field in ("creators_client_id", "creators_client_secret", "partner_tag"):
                if not getattr(cfg, field):
                    raise ConfigError(
                        f"PRICE_SOURCE=creators requires {field.upper()} to be set")
        return cfg
