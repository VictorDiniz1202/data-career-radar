"""Canonical, provider-agnostic models for ingested job data.

Every source adapter must map its raw payload
into these models, so downstream stages never depend on a provider's schema.
"""

from datetime import datetime, timezone
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from career_radar.normalization.location import CountryCode, normalize_location


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobPosting(BaseModel):
    """A single job ad as observed at a point in time."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(description="Provider identifier, e.g. 'greenhouse'.")
    board_slug: str = Field(description="Company board identifier at the provider.")
    external_id: str = Field(description="Provider-side job id, kept as string.")
    title: str
    location: str | None = Field(
        default=None,
        description="Raw location text, preserved as published.",
    )
    url: HttpUrl = Field(description="Absolute URL of the job ad.")
    is_remote: bool = Field(default=False, description="Remote hint, not eligibility.")
    country_code: CountryCode | None = Field(default=None)
    updated_at: datetime | None = Field(
        default=None, description="Last update timestamp reported by the provider."
    )
    content: str | None = Field(
        default=None, description="Raw description as returned by the provider."
    )
    collected_at: datetime = Field(
        default_factory=_utcnow, description="Instant (UTC) this record was observed."
    )

    @model_validator(mode="after")
    def normalize_location_fields(self) -> Self:
        normalized = normalize_location(self.location, self.is_remote)
        object.__setattr__(self, "is_remote", normalized.is_remote)
        object.__setattr__(self, "country_code", normalized.country_code)
        return self


class CompanyBoard(BaseModel):
    """A company's public job board and the postings collected from it."""

    source: str
    board_slug: str
    postings: list[JobPosting] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=_utcnow)
