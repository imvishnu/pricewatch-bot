"""Price poller — run periodically by a systemd timer (or cron).

Flow: group active trackings by ASIN → fetch each product once → snapshot
price → update product metadata → per tracking: apply the user's category
filter, evaluate compare logic, send a Telegram alert with an affiliate
link if warranted, and record it in alerts_sent.

Run: python -m pricewatch.poller
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from . import compare, db
from .config import Config
from .notify.telegram import TelegramNotifier
from .sources.creators import CreatorsAPISource

log = logging.getLogger(__name__)

# Creators API starter limit is 1 TPS / 8640 requests per day —
# sleep a bit over 1s between fetches to stay under it.
FETCH_INTERVAL_S = 1.1


def format_alert(title: str, asin: str, price: float, baseline: float,
                 drop_pct: float, link: str) -> str:
    return (
        f"📉 Price drop: {title or asin}\n"
        f"Now ₹{price:,.2f} — {drop_pct:.0f}% below the 90-day median "
        f"(₹{baseline:,.2f})\n{link}"
    )


async def run_once(conn, source: CreatorsAPISource, notifier: TelegramNotifier) -> None:
    trackings = db.list_active_trackings(conn)
    by_asin: dict[str, list[db.ActiveTracking]] = defaultdict(list)
    for t in trackings:
        by_asin[t.asin].append(t)
    log.info("polling %d products across %d trackings", len(by_asin), len(trackings))

    first = True
    for asin, asin_trackings in by_asin.items():
        if not first:
            await asyncio.sleep(FETCH_INTERVAL_S)
        first = False

        try:
            result = await source.fetch(asin)
        except Exception as exc:  # noqa: BLE001 — skip product, keep polling
            log.warning("fetch failed for %s: %s", asin, exc)
            continue

        db.add_snapshot(conn, asin, result.price, result.currency)
        db.upsert_product(conn, asin, result.title, result.category)
        window = db.recent_prices(conn, asin)

        for t in asin_trackings:
            # Per-user category filter: empty set means all categories.
            cats = db.get_user_categories(conn, t.user_id)
            if cats and result.category not in cats:
                continue

            decision = compare.evaluate(
                current_price=result.price,
                window_prices=window,
                threshold_pct=t.threshold_pct,
                last_alerted_price=db.last_alerted_price(conn, t.tracking_id),
            )
            if not decision.should_alert:
                log.debug("no alert for tracking %d (%s): %s",
                          t.tracking_id, asin, decision.reason)
                continue

            text = format_alert(result.title, asin, result.price,
                                decision.baseline, decision.drop_pct,
                                source.affiliate_link(asin))
            if await notifier.send(str(t.telegram_id), text):
                db.record_alert(conn, t.tracking_id, result.price, decision.baseline)
                log.info("alerted tracking %d for %s at %.2f",
                         t.tracking_id, asin, result.price)


async def amain() -> None:
    config = Config.from_env()
    conn = db.connect(config.database_url)
    source = CreatorsAPISource(config.creators_client_id,
                               config.creators_client_secret,
                               config.partner_tag)
    notifier = TelegramNotifier(config.telegram_bot_token)
    try:
        await run_once(conn, source, notifier)
    finally:
        await source.aclose()
        await notifier.aclose()
        conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(amain())


if __name__ == "__main__":
    main()
