"""Telegram bot — /start, /track, /categories, /list.

Long-running process (systemd service). Run: python -m pricewatch.bot
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import db
from .asin import (DEFAULT_THRESHOLD_PCT, clamp_threshold, is_wishlist_link,
                   resolve_asin)
from .config import Config
from .sources.scraper import ScraperError, ScraperSource

log = logging.getLogger(__name__)

HELP = (
    "I watch Amazon.in prices and alert you on real drops.\n\n"
    "/track <amazon url, wish-list link or ASIN> [drop%] — track a product "
    f"or a whole list (default {DEFAULT_THRESHOLD_PCT}% below 90-day median)\n"
    "/categories electronics, shoes — only alert for these categories "
    "(empty clears the filter)\n"
    "/list — show what you're tracking\n\n"
    "Note: alerts start once a product has ~10 days of price history."
)


def _conn(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["conn"]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db.upsert_user(_conn(context), update.effective_user.id)
    await update.message.reply_text("Welcome to pricewatch!\n\n" + HELP)


async def cmd_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = _conn(context)
    user_id = db.upsert_user(conn, update.effective_user.id)

    if not context.args:
        await update.message.reply_text(
            "Usage: /track <amazon url or ASIN> [drop%]")
        return

    target = context.args[0]
    threshold = float(DEFAULT_THRESHOLD_PCT)
    if len(context.args) > 1:
        try:
            threshold = clamp_threshold(float(context.args[1].rstrip("%")))
        except ValueError:
            await update.message.reply_text(
                f"Couldn't parse '{context.args[1]}' as a percentage.")
            return

    # Whole wish list: import every product on it.
    if is_wishlist_link(target):
        scraper = ScraperSource()
        try:
            list_name, asins = await scraper.fetch_wishlist(target)
        except ScraperError as exc:
            await update.message.reply_text(f"Couldn't read that list: {exc}")
            return
        finally:
            await scraper.aclose()
        for asin in asins:
            db.upsert_product(conn, asin)
            db.upsert_tracking(conn, user_id, asin, threshold)
        await update.message.reply_text(
            f"Imported {len(asins)} products from “{list_name}” — tracking "
            f"each at ≥{threshold:.0f}% below its 90-day median. See /list.")
        return

    asin = await resolve_asin(target)
    if not asin:
        await update.message.reply_text(
            "Couldn't find an ASIN in that. Send an amazon.in product link, "
            "an amzn.in short link, a wish-list share link, or a "
            "10-character ASIN.")
        return

    db.upsert_product(conn, asin)
    db.upsert_tracking(conn, user_id, asin, threshold)
    await update.message.reply_text(
        f"Tracking {asin} — I'll alert you when it drops ≥{threshold:.0f}% "
        "below its 90-day median price.")


async def cmd_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = _conn(context)
    user_id = db.upsert_user(conn, update.effective_user.id)

    raw = " ".join(context.args)
    categories = [c.strip().lower() for c in raw.split(",") if c.strip()]
    db.set_user_categories(conn, user_id, categories)
    if categories:
        await update.message.reply_text(
            "Category filter set: " + ", ".join(categories))
    else:
        await update.message.reply_text(
            "Category filter cleared — alerting for all categories.")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = _conn(context)
    user_id = db.upsert_user(conn, update.effective_user.id)

    rows = db.list_trackings_for_user(conn, user_id)
    if not rows:
        await update.message.reply_text(
            "You're not tracking anything yet. Use /track to add a product.")
        return
    lines = []
    for r in rows:
        title = r["title"] or r["asin"]
        cat = f" [{r['category']}]" if r["category"] else ""
        lines.append(f"• {title}{cat} — alert at ≥{float(r['threshold_pct']):.0f}% drop "
                     f"({r['asin']})")
    cats = db.get_user_categories(conn, user_id)
    if cats:
        lines.append("\nCategory filter: " + ", ".join(cats))
    await update.message.reply_text("\n".join(lines))


def build_app(config: Config) -> Application:
    app = Application.builder().token(config.telegram_bot_token).build()
    app.bot_data["conn"] = db.connect(config.database_url)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("track", cmd_track))
    app.add_handler(CommandHandler("categories", cmd_categories))
    app.add_handler(CommandHandler("list", cmd_list))
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = Config.from_env()
    app = build_app(config)
    log.info("pricewatch bot starting (polling)")
    app.run_polling()


if __name__ == "__main__":
    main()
