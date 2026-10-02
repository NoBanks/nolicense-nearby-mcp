"""MCP server for the No License Nearby sync licensing catalog."""

from __future__ import annotations

import json
import math
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError

from .client import NoLicenseAPIError, NoLicenseClient
from .schemas import (
    CATEGORY_TO_TIER,
    GetLicenseCheckoutLinkInput,
    GetPreviewUrlInput,
    GetTrackInput,
    ListLicenseTiersInput,
    QuoteLicenseInput,
    SearchTracksInput,
    TIER_LABELS,
    TIER_SCOPES,
)

SERVER_INSTRUCTIONS = (
    "No License Nearby is an artist-owned sync licensing catalog of 882 tracks where the artist "
    "owns 100% of every master and every publishing share, so one license clears the music. "
    "These tools let you search the catalog, audition tracks, see live prices and build a quote. "
    "Buying happens on the No License Nearby website by submitting a license request; this MCP "
    "never submits license requests and never takes payment. No API key is needed."
)

USAGE_DURATIONS = ["one-time", "six-months", "one-year", "perpetual"]

CUSTOM_QUOTE_NOTE = (
    "Projects outside these tiers: choose 'Something else' on the license page for a custom quote."
)

QUOTE_NOTE = (
    "Estimate matches the site's calculator. The final invoice is issued after the license "
    "request is reviewed. The license page link pre-fills the first track; the other tracks are "
    "added on the form."
)

PREVIEW_NOTE = "Listening is free. Using this track in any project requires a license: {url}"

HOW_IT_WORKS = [
    "Open the link; the track is pre-filled.",
    "Choose '{label}' as the project type and a usage duration.",
    "Describe the project, agree to the terms, and submit the license request.",
    "You receive an invoice after review; usage rights activate after payment.",
]

server = Server("nolicense-mcp", instructions=SERVER_INSTRUCTIONS)

_client = NoLicenseClient()


def _error(code: Any, message: str, hint: str) -> list[types.TextContent]:
    payload = {"error": {"code": code, "message": message, "hint": hint}}
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


def _result(data: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _encode_artwork(url: Any) -> Any:
    if not url:
        return None
    from urllib.parse import quote

    return quote(str(url), safe=":/?#[]@!$&'()*+,;=%")


def _compact_track(track: dict) -> dict:
    bpm = track.get("bpm") or None
    return {
        "track_id": track.get("id"),
        "title": track.get("title"),
        "genre": track.get("genre"),
        "mood": track.get("mood"),
        "duration": track.get("duration"),
        "bpm": bpm,
        "energy": track.get("energy"),
        "camelot_key": track.get("camelotKey"),
        "artwork_url": _encode_artwork(track.get("imageUrl")),
        "license_page_url": _client.license_page_url(str(track.get("title") or "")),
    }


async def _run_search(args: SearchTracksInput) -> dict:
    catalog = await _client.all_tracks()
    visible = [t for t in catalog if t.get("visible")]

    total_tracks = len(visible)
    unknown_bpm = sum(1 for t in visible if not t.get("bpm"))
    unknown_energy = sum(1 for t in visible if t.get("energy") is None)

    warnings: list[str] = []
    matches = []
    bpm_filtered = False
    energy_excluded = 0

    for t in visible:
        if args.query is not None:
            if args.query.lower() not in str(t.get("title") or "").lower():
                continue
        if args.genre is not None:
            if str(t.get("genre") or "").lower() != args.genre.lower():
                continue
        if args.mood is not None:
            if str(t.get("mood") or "").lower() != args.mood.lower():
                continue
        if args.camelot_key is not None:
            if str(t.get("camelotKey") or "").lower() != args.camelot_key.lower():
                continue
        if args.use_case is not None:
            track_use = str(t.get("useCase") or "")
            if track_use != "all" and track_use != args.use_case:
                continue
        if args.bpm_min is not None or args.bpm_max is not None:
            bpm = t.get("bpm")
            if not bpm:
                bpm_filtered = True
                continue
            if args.bpm_min is not None and bpm < args.bpm_min:
                continue
            if args.bpm_max is not None and bpm > args.bpm_max:
                continue
        if args.energy_min is not None or args.energy_max is not None:
            energy = t.get("energy")
            if energy is None:
                energy_excluded += 1
                continue
            if args.energy_min is not None and energy < args.energy_min:
                continue
            if args.energy_max is not None and energy > args.energy_max:
                continue
        matches.append(t)

    if (args.bpm_min is not None or args.bpm_max is not None) and bpm_filtered:
        warnings.append(
            f"BPM is not populated in the catalog yet ({unknown_bpm} of {total_tracks} tracks "
            "have bpm 0), so tempo filtering excluded them. Try mood or energy instead."
        )
    if (args.energy_min is not None or args.energy_max is not None) and energy_excluded:
        warnings.append(
            f"Energy is not populated for every track yet ({unknown_energy} of {total_tracks} "
            "tracks have no energy value), so energy filtering excluded them."
        )

    total_matches = len(matches)
    page = matches[args.offset : args.offset + args.limit]

    genres = sorted({str(t.get("genre")) for t in visible if t.get("genre")})
    moods = sorted({str(t.get("mood")) for t in visible if t.get("mood")})

    return {
        "total_matches": total_matches,
        "offset": args.offset,
        "limit": args.limit,
        "tracks": [_compact_track(t) for t in page],
        "warnings": warnings,
        "available_filters": {"genres": genres, "moods": moods},
    }


async def _run_get_track(args: GetTrackInput) -> dict:
    t = await _client.track(args.track_id)
    if not t.get("visible"):
        raise NoLicenseAPIError(status=404, message="Track not found")
    return {
        "track_id": t.get("id"),
        "title": t.get("title"),
        "genre": t.get("genre"),
        "mood": t.get("mood"),
        "duration": t.get("duration"),
        "bpm": t.get("bpm") or None,
        "energy": t.get("energy"),
        "camelot_key": t.get("camelotKey"),
        "mood_tags": t.get("moodTags"),
        "has_vocals": t.get("hasVocals"),
        "use_case": t.get("useCase"),
        "artwork_url": _encode_artwork(t.get("imageUrl")),
        "created_at": t.get("createdAt"),
        "license_page_url": _client.license_page_url(str(t.get("title") or "")),
    }


async def _run_get_preview_url(args: GetPreviewUrlInput) -> dict:
    data = await _client.secure_url(args.track_id)
    track = await _client.track(args.track_id)
    license_url = _client.license_page_url(str(track.get("title") or ""))
    return {
        "track_id": data.get("trackId", args.track_id),
        "preview_url": data.get("secureUrl"),
        "content_type": data.get("contentType"),
        "format": data.get("format"),
        "license_required": True,
        "note": PREVIEW_NOTE.format(url=license_url),
    }


def _tier_entry(item: dict) -> dict:
    category = str(item.get("category") or "")
    tier = CATEGORY_TO_TIER.get(category, category)
    label = TIER_LABELS.get(tier, category)
    scope = TIER_SCOPES.get(tier)
    cents = int(item.get("basePrice") or 0)
    return {
        "tier": tier,
        "label": label,
        "scope": scope,
        "price_per_track_usd": cents / 100,
        "price_per_track_cents": cents,
        "bulk_discount_percent": item.get("bulkDiscount"),
        "bulk_discount_min_tracks": item.get("minTracksForDiscount"),
    }


async def _run_list_license_tiers(args: ListLicenseTiersInput) -> dict:
    pricing = await _client.pricing()
    return {
        "currency": "USD",
        "tiers": [_tier_entry(p) for p in pricing],
        "custom_quote": CUSTOM_QUOTE_NOTE,
        "usage_durations": list(USAGE_DURATIONS),
        "pricing_page_url": f"{_client.base_url}/pricing",
        "license_page_url": f"{_client.base_url}/license",
    }


def _find_pricing(pricing: list[dict], tier: str) -> dict | None:
    from .schemas import TIER_TO_CATEGORY

    category = TIER_TO_CATEGORY[tier]
    for p in pricing:
        if p.get("category") == category:
            return p
    return None


async def _run_quote_license(args: QuoteLicenseInput) -> dict:
    pricing = await _client.pricing()
    price_row = _find_pricing(pricing, args.tier)
    if price_row is None:
        raise NoLicenseAPIError(status=500, message=f"Pricing tier '{args.tier}' not available")

    catalog = await _client.all_tracks()
    by_id = {t.get("id"): t for t in catalog if t.get("visible")}
    missing = [tid for tid in args.track_ids if tid not in by_id]
    if missing:
        raise ValueError(f"Unknown or unavailable track ids: {missing}. No partial quote was made.")

    tracks = [by_id[tid] for tid in args.track_ids]
    n = len(tracks)
    per_track_usd = int(price_row.get("basePrice") or 0) / 100
    gross_usd = per_track_usd * n
    bulk_discount = int(price_row.get("bulkDiscount") or 0)
    min_tracks = int(price_row.get("minTracksForDiscount") or 0)
    discount_applied = n >= min_tracks
    if discount_applied:
        estimate_usd = math.floor(gross_usd * (100 - bulk_discount) / 100 + 0.5)
    else:
        estimate_usd = gross_usd

    first_title = str(tracks[0].get("title") or "")
    return {
        "tier": args.tier,
        "label": TIER_LABELS[args.tier],
        "tracks": [{"track_id": t.get("id"), "title": t.get("title")} for t in tracks],
        "track_count": n,
        "price_per_track_usd": per_track_usd,
        "gross_usd": gross_usd,
        "bulk_discount_applied": discount_applied,
        "bulk_discount_percent": bulk_discount,
        "estimate_usd": estimate_usd,
        "currency": "USD",
        "is_estimate": True,
        "note": QUOTE_NOTE,
        "license_page_url": _client.license_page_url(first_title),
    }


async def _run_get_license_checkout_link(args: GetLicenseCheckoutLinkInput) -> dict:
    track = await _client.track(args.track_id)
    if not track.get("visible"):
        raise NoLicenseAPIError(status=404, message="Track not found")
    pricing = await _client.pricing()
    price_row = _find_pricing(pricing, args.tier)
    if price_row is None:
        raise NoLicenseAPIError(status=500, message=f"Pricing tier '{args.tier}' not available")
    title = str(track.get("title") or "")
    label = TIER_LABELS[args.tier]
    return {
        "track_id": track.get("id"),
        "title": title,
        "tier": args.tier,
        "label": label,
        "price_per_track_usd": int(price_row.get("basePrice") or 0) / 100,
        "checkout_url": _client.license_page_url(title),
        "how_it_works": [step.format(label=label) for step in HOW_IT_WORKS],
        "payment_taken_by_mcp": False,
    }


_TOOLS: dict[str, dict[str, Any]] = {
    "search_tracks": {
        "description": (
            "Use this when the user wants to find licensable music by mood, genre, energy, key, "
            "or title words."
        ),
        "model": SearchTracksInput,
        "handler": _run_search,
    },
    "get_track": {
        "description": "Use this when the user wants the full details of one track.",
        "model": GetTrackInput,
        "handler": _run_get_track,
    },
    "get_preview_url": {
        "description": (
            "Use this when the user wants to listen to (audition) a track. The URL is for "
            "auditioning only; any use of the track in a project requires a license."
        ),
        "model": GetPreviewUrlInput,
        "handler": _run_get_preview_url,
    },
    "list_license_tiers": {
        "description": (
            "Use this when the user asks what licenses cost or which license fits their project."
        ),
        "model": ListLicenseTiersInput,
        "handler": _run_list_license_tiers,
    },
    "quote_license": {
        "description": (
            "Use this when the user wants a price estimate for licensing specific tracks for a use."
        ),
        "model": QuoteLicenseInput,
        "handler": _run_quote_license,
    },
    "get_license_checkout_link": {
        "description": (
            "Use this when the user is ready to buy a license for a track. There is no instant "
            "checkout: the human requests and pays the license on the No License Nearby website. "
            "This tool never submits anything and never takes payment."
        ),
        "model": GetLicenseCheckoutLinkInput,
        "handler": _run_get_license_checkout_link,
    },
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=spec["description"],
            inputSchema=spec["model"].model_json_schema(),
        )
        for name, spec in _TOOLS.items()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    spec = _TOOLS.get(name)
    if spec is None:
        return _error(
            "unknown_tool",
            f"Unknown tool: {name}",
            f"Available tools: {', '.join(sorted(_TOOLS))}.",
        )

    try:
        args = spec["model"].model_validate(arguments or {})
    except ValidationError as exc:
        return _error("validation", str(exc), str(exc))

    try:
        result = await spec["handler"](args)
    except NoLicenseAPIError as exc:
        if exc.status == 404:
            return _error(
                "not_found",
                exc.message,
                "Track not found. Use search_tracks to find valid track ids.",
            )
        if exc.status == 0:
            return _error(
                "network",
                exc.message,
                "Could not reach https://license.nomusicnearby.com (check NOLICENSE_API_BASE "
                "and your connection).",
            )
        return _error(
            exc.status,
            exc.message,
            "The No License Nearby catalog had a server error; try again shortly.",
        )
    except ValueError as exc:
        return _error("validation", str(exc), str(exc))

    return _result(result)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main_sync() -> None:
    import asyncio

    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
