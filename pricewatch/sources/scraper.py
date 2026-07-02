"""Scraper price source — reads prices directly from amazon.in product pages.

No affiliate/Creators credentials needed. Fragile by nature (Amazon changes
markup and may serve CAPTCHA pages under load) — failures raise ScraperError
and the poller logs and skips that product for the run.
"""

from __future__ import annotations

import asyncio
import re

import httpx
from selectolax.parser import HTMLParser

from .base import PriceResult, PriceSource

BASE_URL = "https://www.amazon.in"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Tried in order — Amazon varies layouts across categories/experiments.
PRICE_SELECTORS = [
    ".a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "span.a-price-whole",
]

_PRICE_CLEAN_RE = re.compile(r"[^\d.]")


class ScraperError(RuntimeError):
    pass


def parse_price_text(text: str) -> float:
    """'₹1,29,900.00' -> 129900.0"""
    cleaned = _PRICE_CLEAN_RE.sub("", text.strip())
    if not cleaned:
        raise ScraperError(f"no digits in price text: {text!r}")
    return float(cleaned)


def parse_product_page(html: str, asin: str) -> PriceResult:
    """Parse an amazon.in product page. Raises ScraperError on block/shape issues."""
    tree = HTMLParser(html)

    page_title = tree.css_first("title")
    if page_title and "robot check" in page_title.text().lower():
        raise ScraperError(f"bot-blocked (CAPTCHA page) for {asin}")

    price_node = None
    for sel in PRICE_SELECTORS:
        price_node = tree.css_first(sel)
        if price_node and price_node.text(strip=True):
            break
    if not price_node or not price_node.text(strip=True):
        raise ScraperError(f"no price found on page for {asin}")
    price = parse_price_text(price_node.text())

    title_node = tree.css_first("#productTitle")
    title = title_node.text(strip=True) if title_node else ""

    crumb = tree.css_first("#wayfinding-breadcrumbs_feature_div a")
    category = crumb.text(strip=True).lower() if crumb else ""

    return PriceResult(asin=asin, price=price, currency="INR",
                       title=title, category=category)


class ScraperSource(PriceSource):
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(
            timeout=20, headers=HEADERS, follow_redirects=True)

    def product_link(self, asin: str) -> str:
        return f"{BASE_URL}/dp/{asin}"

    async def fetch(self, asin: str) -> PriceResult:
        url = self.product_link(asin)
        resp = await self._client.get(url)
        if resp.status_code == 503:
            # transient throttle — back off once and retry
            await asyncio.sleep(5)
            resp = await self._client.get(url)
        if resp.status_code != 200:
            raise ScraperError(f"HTTP {resp.status_code} for {asin}")
        return parse_product_page(resp.text, asin)

    async def aclose(self) -> None:
        await self._client.aclose()
