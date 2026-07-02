"""Amazon Creators API price source (amazon.in marketplace).

This targets Amazon's Creators API — OAuth 2.0 client-credentials with
camelCase JSON fields — NOT the retired PA-API 5.0 (which used AWS SigV4
request signing).

The exact request/response shapes below MUST be verified against the
Associates Central / Creators API documentation before production use;
every uncertain spot is marked `# confirm against docs`.
"""

from __future__ import annotations

import time

import httpx

from .base import PriceResult, PriceSource

MARKETPLACE = "www.amazon.in"

# confirm against docs: OAuth token endpoint URL
TOKEN_URL = "https://api.amazon.com/auth/o2/token"
# confirm against docs: OAuth scope for the Creators API
TOKEN_SCOPE = "creators::catalog:read"
# confirm against docs: Creators API base URL and items endpoint path
API_BASE = "https://creators.api.amazon.com"
ITEMS_PATH = "/catalog/v1/items"


class CreatorsAPIError(RuntimeError):
    pass


class CreatorsAPISource(PriceSource):
    """Fetches prices via the Creators API using OAuth2 client-credentials."""

    def __init__(self, client_id: str, client_secret: str, partner_tag: str,
                 client: httpx.AsyncClient | None = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._partner_tag = partner_tag
        self._client = client or httpx.AsyncClient(timeout=15)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at - 60:
            return self._token
        resp = await self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": TOKEN_SCOPE,  # confirm against docs: scope parameter name/value
            },
        )
        if resp.status_code != 200:
            raise CreatorsAPIError(f"token request failed: {resp.status_code} {resp.text[:200]}")
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.monotonic() + float(payload.get("expires_in", 3600))
        return self._token

    async def fetch(self, asin: str) -> PriceResult:
        token = await self._get_token()
        # confirm against docs: endpoint path, query parameter names, and
        # whether partnerTag/marketplace are query params or body fields
        resp = await self._client.get(
            f"{API_BASE}{ITEMS_PATH}/{asin}",
            params={
                "marketplace": MARKETPLACE,
                "partnerTag": self._partner_tag,
                "resources": "itemInfo.title,offers.listings.price,browseNodeInfo",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            raise CreatorsAPIError(f"item request failed for {asin}: "
                                   f"{resp.status_code} {resp.text[:200]}")
        data = resp.json()

        # confirm against docs: response parsing — field names below are the
        # expected camelCase shape but must be checked against real responses.
        try:
            item = data["item"] if "item" in data else data["items"][0]
            title = item["itemInfo"]["title"]["displayValue"]
            listing = item["offers"]["listings"][0]
            price = float(listing["price"]["amount"])
            currency = listing["price"]["currency"]  # expected "INR"
            category = (
                item.get("browseNodeInfo", {})
                    .get("browseNodes", [{}])[0]
                    .get("displayName", "")
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise CreatorsAPIError(f"unexpected response shape for {asin}: {exc}") from exc

        return PriceResult(asin=asin, price=price, currency=currency,
                           title=title, category=category.lower())

    def affiliate_link(self, asin: str) -> str:
        return f"https://{MARKETPLACE}/dp/{asin}?tag={self._partner_tag}"

    async def aclose(self) -> None:
        await self._client.aclose()
