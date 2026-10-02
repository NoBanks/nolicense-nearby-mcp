"""Tests for nolicense-mcp. Import list_tools / call_tool as functions and await them (mcp Server decorators
register handlers; they are not callable methods). All HTTP is mocked with respx; no real network."""

import json

import httpx
import pytest
import respx

from nolicense_mcp import client as client_mod
from nolicense_mcp.server import call_tool, list_tools

BASE = "https://license.nomusicnearby.com"

TRACKS = [
    {"id": 1, "title": "Showerhead", "genre": "electronic", "mood": "chill", "duration": "2:40", "bpm": 0,
     "energy": 3, "camelotKey": "1A", "imageUrl": None, "useCase": "all", "visible": True, "url": "https://x/1.mp3"},
    {"id": 2, "title": "Dat Piano", "genre": "instrumental", "mood": "groove", "duration": "2:19", "bpm": 0,
     "energy": 6, "camelotKey": "4A", "imageUrl": None, "useCase": "all", "visible": True, "url": "https://x/2.mp3"},
    {"id": 3, "title": "Night Drive", "genre": "electronic", "mood": "dark", "duration": "3:01", "bpm": 0,
     "energy": 7, "camelotKey": "8A", "imageUrl": None, "useCase": "all", "visible": True, "url": "https://x/3.mp3"},
    {"id": 4, "title": "Hidden One", "genre": "electronic", "mood": "chill", "duration": "1:00", "bpm": 0,
     "energy": 2, "camelotKey": None, "imageUrl": None, "useCase": "all", "visible": False, "url": "https://x/4.mp3"},
]
PRICING = [
    {"id": 1, "category": "social_media", "basePrice": 9900, "bulkDiscount": 10, "minTracksForDiscount": 3},
    {"id": 2, "category": "tv", "basePrice": 49900, "bulkDiscount": 10, "minTracksForDiscount": 3},
    {"id": 3, "category": "film", "basePrice": 199000, "bulkDiscount": 10, "minTracksForDiscount": 3},
]


def parse(result):
    return json.loads(result[0].text)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("NOLICENSE_API_BASE", raising=False)
    client_mod.clear_cache()
    yield
    client_mod.clear_cache()


def mock_catalog():
    return respx.get(f"{BASE}/api/tracks").mock(
        return_value=httpx.Response(200, json={"tracks": TRACKS, "pagination": {"total": 4}})
    )


@pytest.mark.asyncio
async def test_six_tools_registered():
    names = {t.name for t in await list_tools()}
    assert names == {"search_tracks", "get_track", "get_preview_url", "list_license_tiers",
                     "quote_license", "get_license_checkout_link"}


@pytest.mark.asyncio
@respx.mock
async def test_search_combines_filters_locally_and_sends_user_agent():
    route = mock_catalog()
    result = parse(await call_tool("search_tracks", {"genre": "electronic", "mood": "chill"}))
    assert result["total_matches"] == 1  # hidden track 4 excluded, both filters applied
    assert result["tracks"][0]["title"] == "Showerhead"
    req = route.calls[0].request
    assert req.headers["user-agent"] == "nolicense-nearby-mcp/0.1.0"
    assert req.url.params.get("limit") == "1000"
    assert "genre" not in req.url.params


@pytest.mark.asyncio
@respx.mock
async def test_catalog_is_cached():
    route = mock_catalog()
    await call_tool("search_tracks", {"query": "piano"})
    await call_tool("search_tracks", {"query": "night"})
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_track_not_found():
    respx.get(f"{BASE}/api/tracks/999").mock(return_value=httpx.Response(404, json={"message": "Track not found"}))
    result = parse(await call_tool("get_track", {"track_id": 999}))
    assert result["error"]["code"] == "not_found"


@pytest.mark.asyncio
@respx.mock
async def test_quote_applies_bulk_discount_js_rounding():
    mock_catalog()
    respx.get(f"{BASE}/api/pricing").mock(return_value=httpx.Response(200, json=PRICING))
    result = parse(await call_tool("quote_license", {"track_ids": [1, 2, 3], "tier": "social"}))
    assert result["gross_usd"] == 297.0
    assert result["estimate_usd"] == 267
    assert result["bulk_discount_applied"] is True


@pytest.mark.asyncio
@respx.mock
async def test_list_tiers_reads_live_prices():
    respx.get(f"{BASE}/api/pricing").mock(return_value=httpx.Response(200, json=PRICING))
    result = parse(await call_tool("list_license_tiers", {}))
    prices = {t["tier"]: t["price_per_track_usd"] for t in result["tiers"]}
    assert prices == {"social": 99.0, "tv": 499.0, "film": 1990.0}


@pytest.mark.asyncio
@respx.mock
async def test_checkout_link_prefills_title_and_never_posts():
    respx.get(f"{BASE}/api/tracks/2").mock(return_value=httpx.Response(200, json=TRACKS[1]))
    respx.get(f"{BASE}/api/pricing").mock(return_value=httpx.Response(200, json=PRICING))
    post_route = respx.post(url__startswith=BASE).mock(return_value=httpx.Response(500))
    result = parse(await call_tool("get_license_checkout_link", {"track_id": 2, "tier": "film"}))
    assert result["checkout_url"] == f"{BASE}/license?track=Dat%20Piano"
    assert result["price_per_track_usd"] == 1990.0
    assert not post_route.called


@pytest.mark.asyncio
@respx.mock
async def test_network_error_is_structured():
    respx.get(f"{BASE}/api/pricing").mock(side_effect=httpx.ConnectError("down"))
    result = parse(await call_tool("list_license_tiers", {}))
    assert result["error"]["code"] == "network"
