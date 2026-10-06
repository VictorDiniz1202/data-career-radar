"""Persistence for job postings. Talks to the ingestion layer only via Pydantic models."""

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import insert

from career_radar.ingestion.models import JobPosting
from career_radar.storage.database import UNIQUE_CONSTRAINT_NAME, JobPostingRow

_CHUNK_SIZE = 500


@dataclass(frozen=True)
class UpsertResult:
    inserted: int
    updated: int

    @property
    def total(self) -> int:
        return self.inserted + self.updated


class JobPostingRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _to_row(posting: JobPosting) -> dict:
        return {
            "source": posting.source,
            "external_id": posting.external_id,
            "board_slug": posting.board_slug,
            "title": posting.title,
            "location": posting.location,
            "url": str(posting.url),
            "updated_at": posting.updated_at,
            "content": posting.content,
            "first_seen_at": posting.collected_at,
            "last_seen_at": posting.collected_at,
        }

    def upsert_postings(self, postings: Sequence[JobPosting]) -> UpsertResult:
        """INSERT ... ON CONFLICT DO UPDATE in a single transaction.

        Mutable fields and last_seen_at are refreshed; identity and first_seen_at
        are preserved. Rolls back entirely on any failure.
        """
        # A single INSERT cannot affect the same key twice: dedupe, keeping the last.
        rows = {(p.source, p.board_slug, p.external_id): self._to_row(p) for p in postings}
        if not rows:
            return UpsertResult(0, 0)

        values = list(rows.values())
        inserted = updated = 0
        with self.engine.begin() as conn:
            for start in range(0, len(values), _CHUNK_SIZE):
                stmt = insert(JobPostingRow).values(values[start:start + _CHUNK_SIZE])
                excluded = stmt.excluded
                stmt = stmt.on_conflict_do_update(
                    constraint=UNIQUE_CONSTRAINT_NAME,
                    set_={
                        "title": excluded.title,
                        "location": excluded.location,
                        "url": excluded.url,
                        "updated_at": excluded.updated_at,
                        "content": excluded.content,
                        "last_seen_at": excluded.last_seen_at,
                    },
                ).returning(text("(xmax = 0) AS inserted"))
                for (was_inserted,) in conn.execute(stmt):
                    if was_inserted:
                        inserted += 1
                    else:
                        updated += 1
        return UpsertResult(inserted, updated)
