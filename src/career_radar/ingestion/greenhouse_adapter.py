"""Adapter for the public Greenhouse Job Board API.

Read-only and side-effect free: the same call twice yields equivalent postings
(only ``collected_at`` differs), which keeps this stage safe to re-run.
"""

from datetime import datetime, timezone
from typing import Any

import requests
from pydantic import ValidationError

from career_radar.ingestion.models import CompanyBoard, JobPosting

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs"
SOURCE = "greenhouse"


class GreenhouseError(Exception):
    """Raised when the board cannot be fetched or its payload is unusable."""


class GreenhouseAdapter:
    def __init__(
        self,
        timeout: tuple[float, float] = (5.0, 20.0),
        session: requests.Session | None = None,
    ) -> None:
        # (connect, read) timeouts: never wait indefinitely on the network.
        self.timeout = timeout
        self.session = session or requests.Session()

    def fetch_raw_jobs(self, board_slug: str) -> list[dict[str, Any]]:
        url = GREENHOUSE_URL.format(board_slug=board_slug)
        try:
            response = self.session.get(
                url, params={"content": "true"}, timeout=self.timeout
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise GreenhouseError(f"Timeout fetching board '{board_slug}'") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise GreenhouseError(
                f"HTTP {status} fetching board '{board_slug}'"
            ) from exc
        except (requests.RequestException, ValueError) as exc:
            raise GreenhouseError(
                f"Failed to fetch/parse board '{board_slug}': {exc}"
            ) from exc

        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise GreenhouseError(
                f"Unexpected payload schema for board '{board_slug}': missing 'jobs' list"
            )
        return jobs

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _to_posting(self, board_slug: str, raw: dict[str, Any]) -> JobPosting:
        location = raw.get("location")
        return JobPosting(
            source=SOURCE,
            board_slug=board_slug,
            external_id=str(raw["id"]),
            title=raw["title"],
            location=location.get("name") if isinstance(location, dict) else None,
            url=raw["absolute_url"],
            updated_at=self._parse_datetime(raw.get("updated_at")),
            content=raw.get("content"),
        )

    def fetch_board(self, board_slug: str) -> CompanyBoard:
        """Fetch and normalize every posting. Invalid records fail loudly."""
        raw_jobs = self.fetch_raw_jobs(board_slug)
        postings: list[JobPosting] = []
        invalid: list[str] = []
        for raw in raw_jobs:
            try:
                postings.append(self._to_posting(board_slug, raw))
            except (KeyError, ValidationError, TypeError):
                invalid.append(str(raw.get("id", "<no id>")))
        if invalid:
            # Never drop invalid records silently.
            raise GreenhouseError(
                f"{len(invalid)} invalid record(s) in board '{board_slug}': "
                f"{', '.join(invalid[:10])}"
            )
        return CompanyBoard(source=SOURCE, board_slug=board_slug, postings=postings)
