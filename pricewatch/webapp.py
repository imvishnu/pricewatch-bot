"""Telegram Mini App backend — FastAPI.

Serves the static Mini App (webapp/) and a small JSON API. Every API
request is authenticated by validating Telegram WebApp `initData` (HMAC
signed with the bot token), passed in the `X-Telegram-Init-Data` header.

Run: uvicorn pricewatch.webapp:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from .asin import clamp_threshold, is_wishlist_link, resolve_asin
from .config import Config
from .sources.scraper import ScraperError, ScraperSource

INIT_DATA_MAX_AGE_S = 24 * 3600
WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"


def validate_init_data(init_data: str, bot_token: str,
                       max_age_s: int = INIT_DATA_MAX_AGE_S) -> dict:
    """Validate Telegram WebApp initData; return the parsed user dict.

    Per https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
    hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)
    """
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    their_hash = pairs.pop("hash", None)
    if not their_hash:
        raise ValueError("missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    our_hash = hmac.new(secret_key, data_check_string.encode(),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(our_hash, their_hash):
        raise ValueError("bad signature")

    auth_date = int(pairs.get("auth_date", "0"))
    if max_age_s and time.time() - auth_date > max_age_s:
        raise ValueError("initData expired")

    return json.loads(pairs["user"])


app = FastAPI(title="pricewatch mini app")

# Lazy init so importing this module (e.g. in tests) needs no env/DB.
_state: dict = {}


def _cfg() -> Config:
    if "config" not in _state:
        _state["config"] = Config.from_env()
    return _state["config"]


def _db():
    if "conn" not in _state:
        _state["conn"] = db.connect(_cfg().database_url)
    return _state["conn"]


def auth_user(x_telegram_init_data: str = Header(default="")) -> int:
    """Dependency: returns the internal user id for the request."""
    try:
        tg_user = validate_init_data(x_telegram_init_data,
                                     _cfg().telegram_bot_token)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail=f"auth failed: {exc}") from exc
    return db.upsert_user(_db(), int(tg_user["id"]))


def _num(v):
    return float(v) if v is not None else None


@app.get("/api/tracked")
def api_tracked(user_id: int = Depends(auth_user)):
    rows = db.tracked_with_stats(_db(), user_id)
    out = []
    for r in rows:
        latest, med = _num(r["latest_price"]), _num(r["median_price"])
        drop = ((med - latest) / med * 100) if (latest and med and med > 0) else None
        out.append({
            "asin": r["asin"], "title": r["title"], "category": r["category"],
            "threshold_pct": float(r["threshold_pct"]),
            "latest_price": latest, "median_price": med,
            "snapshot_count": r["snapshot_count"],
            "drop_pct": round(drop, 1) if drop is not None else None,
        })
    return {"tracked": out, "categories": db.get_user_categories(_db(), user_id)}


PRESET_CATEGORIES = [
    "electronics", "computers & accessories", "clothing & accessories",
    "shoes & handbags", "home & kitchen", "beauty", "toys & games",
    "sports, fitness & outdoors", "books", "grocery & gourmet foods",
]


@app.get("/api/deals")
def api_deals(user_id: int = Depends(auth_user)):
    rows = db.list_channel_deals(_db())
    top = db.top_genuine_deals(_db())
    cats = sorted(set(PRESET_CATEGORIES) | set(db.all_known_categories(_db())))
    return {
        "deals": [{
            "asin": r["asin"], "title": r["title"] or r["asin"],
            "category": r["category"], "latest_price": _num(r["latest_price"]),
            "seen_at": r["seen_at"].isoformat(),
        } for r in rows],
        "top_deals": [{
            "asin": r["asin"], "title": r["title"] or r["asin"],
            "category": r["category"], "latest_price": _num(r["latest_price"]),
            "median_price": _num(r["median_price"]),
            "drop_pct": round(float(r["drop_pct"]), 1),
        } for r in top],
        "all_categories": cats,
        "my_categories": db.get_user_categories(_db(), user_id),
    }


@app.get("/api/product/{asin}")
def api_product(asin: str, user_id: int = Depends(auth_user)):
    product = db.product_detail(_db(), asin)
    if not product:
        raise HTTPException(status_code=404, detail="unknown product")
    snaps = db.product_snapshots(_db(), asin)
    return {
        "asin": asin, "title": product["title"], "category": product["category"],
        "snapshots": [{"t": s["captured_at"].isoformat(), "p": float(s["price"])}
                      for s in snaps],
    }


class TrackBody(BaseModel):
    target: str  # url or ASIN
    threshold_pct: float = 50


@app.post("/api/track")
async def api_track(body: TrackBody, user_id: int = Depends(auth_user)):
    threshold = clamp_threshold(body.threshold_pct)

    if is_wishlist_link(body.target):
        scraper = ScraperSource()
        try:
            list_name, asins = await scraper.fetch_wishlist(body.target)
        except ScraperError as exc:
            raise HTTPException(status_code=422,
                                detail=f"couldn't read list: {exc}") from exc
        finally:
            await scraper.aclose()
        for asin in asins:
            db.upsert_product(_db(), asin)
            db.upsert_tracking(_db(), user_id, asin, threshold)
        return {"ok": True, "imported": len(asins), "list_name": list_name,
                "threshold_pct": threshold}

    asin = await resolve_asin(body.target)
    if not asin:
        raise HTTPException(status_code=422, detail="no ASIN found in input")
    db.upsert_product(_db(), asin)
    db.upsert_tracking(_db(), user_id, asin, threshold)
    return {"ok": True, "asin": asin, "threshold_pct": threshold}


@app.post("/api/untrack/{asin}")
def api_untrack(asin: str, user_id: int = Depends(auth_user)):
    db.deactivate_tracking(_db(), user_id, asin)
    return {"ok": True}


class CategoriesBody(BaseModel):
    categories: list[str]


@app.post("/api/categories")
def api_categories(body: CategoriesBody, user_id: int = Depends(auth_user)):
    cats = [c.strip().lower() for c in body.categories if c.strip()]
    db.set_user_categories(_db(), user_id, cats)
    return {"ok": True, "categories": cats}


@app.get("/")
def index():
    return FileResponse(WEBAPP_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")
