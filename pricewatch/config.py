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


@dataclass(frozen=True)
class Config:
    database_url: str
    telegram_bot_token: str
    creators_client_id: str
    creators_client_secret: str
    partner_tag: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            database_url=_require("DATABASE_URL"),
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            creators_client_id=_require("CREATORS_CLIENT_ID"),
            creators_client_secret=_require("CREATORS_CLIENT_SECRET"),
            partner_tag=_require("PARTNER_TAG"),
        )
