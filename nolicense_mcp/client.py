"""Read-only async client for the public No License Nearby API (https://license.nomusicnearby.com).

GET routes only. This client never creates license requests, payment intents or play counts.
"""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_BASE_URL = "https://license.nomusicnearby.com"
USER_AGENT = "nolicense-nearby-mcp/0.1.0"  # Cloudflare blocks default library user agents (verified 2026-10-02)
TIMEOUT = 30.0
CATALOG_TTL_SECONDS = 300.0

# The server applies only the LAST filter when several are combined (verified 2026-10-02), so the whole catalog is
# fetched once and filtered locally. Cache keyed by base URL.
_catalog_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class NoLicenseAPIError(Exception):
    """Raised on any non-2xx response (status = HTTP code) or network failure (status = 0)."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}" if status else message)


def clear_cache() -> None:
    """Drop the cached catalog (used by tests)."""
    _catalog_cache.clear()


class NoLicenseClient:
    """Client for the four public GET routes the MCP is allowed to call."""

    @property
    def base_url(self) -> str:
        return os.environ.get("NOLICENSE_API_BASE", DEFAULT_BASE_URL).rstrip("/")

    def license_page_url(self, title: str) -> str:
        """The real request form, pre-filled with the track title (the form does not accept a tier)."""
        return f"{self.base_url}/license?track={quote(title or '', safe='')}"

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
                response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise NoLicenseAPIError(status=0, message=f"Network error calling {url}: {exc.__class__.__name__}") from exc
        if response.status_code < 200 or response.status_code >= 300:
            message = f"HTTP {response.status_code}"
            try:
                body = response.json()
                if isinstance(body, dict) and isinstance(body.get("message"), str):
                    message = body["message"]
            except ValueError:
                pass
            raise NoLicenseAPIError(status=response.status_code, message=message)
        try:
            return response.json()
        except ValueError as exc:
            raise NoLicenseAPIError(status=response.status_code, message="Response was not JSON") from exc

    async def all_tracks(self) -> list[dict[str, Any]]:
        """GET /api/tracks?limit=1000, cached for 300 seconds."""
        key = self.base_url
        hit = _catalog_cache.get(key)
        if hit and time.monotonic() - hit[0] < CATALOG_TTL_SECONDS:
            return hit[1]
        data = await self._get("/api/tracks", params={"limit": 1000})
        tracks = data.get("tracks", []) if isinstance(data, dict) else []
        if not isinstance(tracks, list):
            tracks = []
        _catalog_cache[key] = (time.monotonic(), tracks)
        return tracks

    async def track(self, track_id: int) -> dict[str, Any]:
        """GET /api/tracks/{id}. Non-numeric ids make the server 500, so callers validate ints first."""
        data = await self._get(f"/api/tracks/{int(track_id)}")
        if not isinstance(data, dict):
            raise NoLicenseAPIError(status=404, message="Track not found")
        return data

    async def secure_url(self, track_id: int) -> dict[str, Any]:
        """GET /api/tracks/{id}/secure-url: the audition (preview) URL."""
        data = await self._get(f"/api/tracks/{int(track_id)}/secure-url")
        return data if isinstance(data, dict) else {}

    async def pricing(self) -> list[dict[str, Any]]:
        """GET /api/pricing: live tiers from the database (never hardcoded)."""
        data = await self._get("/api/pricing")
        return data if isinstance(data, list) else []
