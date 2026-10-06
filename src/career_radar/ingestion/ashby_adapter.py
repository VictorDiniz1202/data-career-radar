"""Read-only adapter for Ashby's public job posting API (single jobs array)."""

import re
from typing import Any

import requests
from pydantic import HttpUrl, TypeAdapter, ValidationError

from career_radar.ingestion.models import CompanyBoard, JobPosting

ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{board_slug}"
_URL = TypeAdapter(HttpUrl)


class AshbyError(Exception):
    """The board could not be collected completely and validated."""


class AshbyAdapter:
    def __init__(
        self,
        timeout: tuple[float, float] = (5.0, 20.0),
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()

    def fetch_raw_jobs(self, board_slug: str) -> list[Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", board_slug):
            raise AshbyError("Invalid Ashby board slug")
        try:
            response = self.session.get(
                ASHBY_URL.format(board_slug=board_slug), timeout=self.timeout
            )
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise AshbyError(f"HTTP {status} fetching Ashby board") from exc
        except (requests.RequestException, ValueError) as exc:
            # Avoid including response bodies or arbitrary upstream messages in logs.
            raise AshbyError("Failed to fetch/parse Ashby board") from exc
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise AshbyError("Unexpected Ashby payload: missing jobs list")
        return jobs

    @staticmethod
    def _to_posting(board_slug: str, raw: dict[str, Any]) -> JobPosting:
        url = _URL.validate_python(raw["jobUrl"])
        external_id = raw.get("id")
        if external_id is None:
            external_id = str(url)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("Invalid posting identity")
        remote = raw.get("isRemote")
        if remote is not None and not isinstance(remote, bool):
            raise ValueError("Invalid remote flag")
        return JobPosting(
            source="ashby",
            board_slug=board_slug,
            external_id=external_id,
            title=raw["title"],
            location=raw.get("location"),
            is_remote=remote is True,
            url=url,
            content=raw.get("descriptionHtml") or raw.get("descriptionPlain"),
        )

    def fetch_board(self, board_slug: str) -> CompanyBoard:
        postings: list[JobPosting] = []
        invalid = 0
        for raw in self.fetch_raw_jobs(board_slug):
            try:
                if not isinstance(raw, dict):
                    raise ValueError("Expected a job object")
                listed = raw.get("isListed", True)
                if not isinstance(listed, bool):
                    raise ValueError("Invalid listing flag")
                if not listed:
                    continue
                postings.append(self._to_posting(board_slug, raw))
            except (KeyError, ValidationError, TypeError, ValueError):
                invalid += 1
        if invalid:
            raise AshbyError(f"{invalid} invalid record(s) in Ashby board")
        return CompanyBoard(source="ashby", board_slug=board_slug, postings=postings)
