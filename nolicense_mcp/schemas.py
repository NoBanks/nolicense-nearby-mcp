"""Pydantic input models and constant maps for the nolicense-mcp tools."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TIER_TO_CATEGORY: dict[str, str] = {
    "social": "social_media",
    "tv": "tv",
    "film": "film",
}

TIER_INFO: dict[str, dict[str, str]] = {
    "social_media": {
        "tier": "social",
        "label": "Social Media",
        "scope": "YouTube, TikTok, Instagram, podcasts, Twitch. Monetized channels included.",
    },
    "tv": {
        "tier": "tv",
        "label": "TV + Streaming",
        "scope": "Episodic TV, streaming originals, docuseries, trailers, network promos.",
    },
    "film": {
        "tier": "film",
        "label": "Film",
        "scope": "Theatrical, festival, and streaming-exclusive films. Indie-friendly.",
    },
}

# Derived maps the server imports (schemas and server were generated separately; keep both shapes in sync).
CATEGORY_TO_TIER: dict[str, str] = {category: info["tier"] for category, info in TIER_INFO.items()}
TIER_LABELS: dict[str, str] = {info["tier"]: info["label"] for info in TIER_INFO.values()}
TIER_SCOPES: dict[str, str] = {info["tier"]: info["scope"] for info in TIER_INFO.values()}

Tier = Literal["social", "tv", "film"]


class SearchTracksInput(BaseModel):
    """Input for search_tracks: find licensable music by mood, genre, energy, key, or title words."""

    query: Annotated[str | None, Field(max_length=200)] = None
    genre: str | None = None
    mood: str | None = None
    bpm_min: Annotated[int | None, Field(ge=1, le=300)] = None
    bpm_max: Annotated[int | None, Field(ge=1, le=300)] = None
    energy_min: Annotated[int | None, Field(ge=1, le=10)] = None
    energy_max: Annotated[int | None, Field(ge=1, le=10)] = None
    camelot_key: Annotated[str | None, Field(pattern=r"^(1[0-2]|[1-9])[ABab]$")] = None
    use_case: Tier | None = None
    limit: Annotated[int, Field(ge=1, le=50)] = 10
    offset: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def check_bounds(self) -> "SearchTracksInput":
        if self.bpm_min is not None and self.bpm_max is not None and self.bpm_min > self.bpm_max:
            raise ValueError("bpm_min must be less than or equal to bpm_max")
        if (
            self.energy_min is not None
            and self.energy_max is not None
            and self.energy_min > self.energy_max
        ):
            raise ValueError("energy_min must be less than or equal to energy_max")
        return self


class GetTrackInput(BaseModel):
    """Input for get_track: full details of one track."""

    track_id: Annotated[int, Field(ge=1)]


class GetPreviewUrlInput(BaseModel):
    """Input for get_preview_url: audition a track."""

    track_id: Annotated[int, Field(ge=1)]


class ListLicenseTiersInput(BaseModel):
    """Input for list_license_tiers: no parameters."""


class QuoteLicenseInput(BaseModel):
    """Input for quote_license: price estimate for licensing specific tracks for a use."""

    track_ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=1, max_length=50)]
    tier: Tier

    @field_validator("track_ids")
    @classmethod
    def dedupe_track_ids(cls, value: list[int]) -> list[int]:
        seen: set[int] = set()
        result: list[int] = []
        for track_id in value:
            if track_id not in seen:
                seen.add(track_id)
                result.append(track_id)
        return result


class GetLicenseCheckoutLinkInput(BaseModel):
    """Input for get_license_checkout_link: hand the human the license page for a track."""

    track_id: Annotated[int, Field(ge=1)]
    tier: Tier
