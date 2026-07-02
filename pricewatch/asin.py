"""ASIN extraction from Amazon URLs or bare ASINs.

Handles:
- https://www.amazon.in/<slug>/dp/B0XXXXXXXX/...
- https://www.amazon.in/gp/product/B0XXXXXXXX
- short links: https://amzn.in/d/XXXXXXX (resolved via HTTP redirect)
- bare 10-character ASINs: B0XXXXXXXX
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
_DP_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:[/?]|$)", re.IGNORECASE)

DEFAULT_THRESHOLD_PCT = 50
MIN_THRESHOLD_PCT = 1
MAX_THRESHOLD_PCT = 95


def clamp_threshold(value: float) -> float:
    """Clamp a drop-percentage threshold to the allowed [1, 95] range."""
    return max(MIN_THRESHOLD_PCT, min(MAX_THRESHOLD_PCT, value))


def extract_asin(text: str) -> str | None:
    """Extract an ASIN from a URL or bare ASIN string. Returns None if not found.

    Does NOT resolve short links; use `resolve_asin` for that.
    """
    text = text.strip()

    # Bare ASIN
    if ASIN_RE.match(text.upper()) and any(c.isdigit() for c in text):
        return text.upper()

    # URL path patterns: /dp/ASIN, /gp/product/ASIN
    m = _DP_RE.search(text)
    if m:
        return m.group(1).upper()
    return None


def is_short_link(text: str) -> bool:
    """True for amzn.in / amzn.to short links that need redirect resolution."""
    try:
        host = urlparse(text.strip() if "://" in text else f"https://{text.strip()}").netloc
    except ValueError:
        return False
    return host.lower().removeprefix("www.") in {"amzn.in", "amzn.to", "amzn.eu"}


async def resolve_asin(text: str, client: httpx.AsyncClient | None = None) -> str | None:
    """Extract an ASIN, following amzn.in/d/... short-link redirects if needed."""
    asin = extract_asin(text)
    if asin:
        return asin
    if not is_short_link(text):
        return None

    url = text.strip() if "://" in text else f"https://{text.strip()}"
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(follow_redirects=True, timeout=10)
    try:
        resp = await client.get(url)
        return extract_asin(str(resp.url))
    except httpx.HTTPError:
        return None
    finally:
        if own_client:
            await client.aclose()
