"""Channel watcher — relays deals from a Telegram channel to opted-in users.

Uses a *user* account via Telethon (MTProto), because bots cannot join
channels they aren't added to. Your account must already be a member of the
watched channel (join via its invite link in your Telegram app first).

Flow: new channel post → extract Amazon link/ASIN → scrape the product to
get its category → send the deal via the bot to users who EXPLICITLY opted
into that category with /categories (strict opt-in: users with no filter
get nothing). De-duped per ASIN via the channel_deals table.

First run (interactive login, creates the session file):
    python -m pricewatch.channelwatch --login
Then run as a service:
    python -m pricewatch.channelwatch

Extra env vars: TG_API_ID, TG_API_HASH (from https://my.telegram.org),
TG_SESSION (session file path), WATCH_CHANNEL (invite link, @name or id).

Note: automated reading with a user account is a gray area under Telegram's
ToS; keep it to personal scale.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest

from . import db
from .asin import extract_asin, is_short_link, resolve_asin
from .config import Config, ConfigError
from .notify.telegram import TelegramNotifier
from .sources.scraper import ScraperSource

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+|amzn\.\w+/\S+")


def _channel_env() -> tuple[int, str, str, list[str]]:
    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()
    session = os.environ.get("TG_SESSION", "channelwatch.session").strip()
    # WATCH_CHANNELS: comma-separated @usernames/links; falls back to the
    # legacy singular WATCH_CHANNEL.
    raw = (os.environ.get("WATCH_CHANNELS", "").strip()
           or os.environ.get("WATCH_CHANNEL", "").strip())
    channels = [c.strip() for c in raw.split(",") if c.strip()]
    if not (api_id and api_hash and channels):
        raise ConfigError("channelwatch requires TG_API_ID, TG_API_HASH and "
                          "WATCH_CHANNELS (comma-separated links/@usernames)")
    return int(api_id), api_hash, session, channels


async def extract_deal_asin(text: str) -> str | None:
    """Find the first Amazon product reference in a post's text."""
    for candidate in _URL_RE.findall(text or ""):
        candidate = candidate.rstrip(").,]")
        if extract_asin(candidate) or is_short_link(candidate):
            asin = await resolve_asin(candidate)
            if asin:
                return asin
    return None


def format_deal(title: str, asin: str, price: float, category: str,
                link: str) -> str:
    return (f"🔥 Deal spotted ({category})\n"
            f"{title or asin}\n"
            f"Current price: ₹{price:,.2f}\n{link}")


async def handle_post(conn, source: ScraperSource, notifier: TelegramNotifier,
                      msg_id: int, text: str) -> None:
    asin = await extract_deal_asin(text)
    if not asin:
        return

    try:
        result = await source.fetch(asin)
    except Exception as exc:  # noqa: BLE001 — skip this post
        log.warning("scrape failed for channel deal %s: %s", asin, exc)
        return

    # Every spotted deal feeds the shared price-history pool, so channel
    # products accumulate snapshots and can surface in "Top genuine deals".
    db.upsert_product(conn, asin, result.title, result.category)
    db.add_snapshot(conn, asin, result.price, result.currency)

    if not result.category:
        log.info("deal %s has no category — nobody to notify", asin)
        return

    if not db.try_claim_channel_deal(conn, msg_id, asin, result.category):
        log.info("deal %s already relayed — skipping", asin)
        return

    recipients = db.users_opted_into_category(conn, result.category)
    sent = 0
    text_out = format_deal(result.title, asin, result.price, result.category,
                           source.product_link(asin))
    for tg_id in recipients:
        if await notifier.send(str(tg_id), text_out):
            sent += 1
    db.set_channel_deal_relay_count(conn, asin, sent)
    log.info("relayed deal %s (%s) to %d/%d opted-in users",
             asin, result.category, sent, len(recipients))


async def amain(login_only: bool = False) -> None:
    config = Config.from_env()
    api_id, api_hash, session, channels = _channel_env()

    client = TelegramClient(session, api_id, api_hash)
    await client.start()  # interactive phone/code prompt on first run
    me = await client.get_me()
    log.info("logged in as %s (%s)", me.first_name, me.id)
    if login_only:
        print("Login OK — session saved. Now run without --login as a service.")
        await client.disconnect()
        return

    entities = []
    for channel in channels:
        try:
            entity = await client.get_entity(channel)
            # Public channels can be joined automatically (idempotent).
            try:
                await client(JoinChannelRequest(entity))
            except Exception:  # noqa: BLE001 — already a member / private
                pass
            entities.append(entity)
            log.info("watching channel: %s", getattr(entity, "title", channel))
        except Exception as exc:  # noqa: BLE001 — keep watching the rest
            log.error("cannot watch %s: %s", channel, exc)
    if not entities:
        raise ConfigError("no watchable channels resolved")

    conn = db.connect(config.database_url)
    source = ScraperSource()
    notifier = TelegramNotifier(config.telegram_bot_token)

    @client.on(events.NewMessage(chats=entities))
    async def _on_post(event):  # noqa: ANN001
        try:
            await handle_post(conn, source, notifier,
                              event.message.id, event.message.message)
        except Exception:  # noqa: BLE001 — never kill the listener
            log.exception("error handling channel post %s", event.message.id)

    await client.run_until_disconnected()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(amain(login_only="--login" in sys.argv))


if __name__ == "__main__":
    main()
