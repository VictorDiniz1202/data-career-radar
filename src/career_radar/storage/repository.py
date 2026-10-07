"""Persist provider-independent Pydantic postings with an atomic UPSERT."""

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import Engine, case, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert

from career_radar.ingestion.models import JobPosting
from career_radar.normalization.job_family import is_data_role
from career_radar.storage.database import UNIQUE_CONSTRAINT_NAME, JobPostingRow

_CHUNK_SIZE = 500
_EVALUATION_FIELDS = (
    "match_score",
    "salary_extracted",
    "match_reason",
    "match_model",
    "evaluated_at",
)


@dataclass(frozen=True)
class PendingPosting:
    """A stored posting that still needs an LLM evaluation."""

    id: int
    title: str
    location: str | None
    country_code: str | None
    url: str
    content: str


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
            "is_remote": posting.is_remote,
            "country_code": posting.country_code,
            "url": str(posting.url),
            "updated_at": posting.updated_at,
            "content": posting.content,
            "is_data_role": is_data_role(posting.title),
            "first_seen_at": posting.collected_at,
            "last_seen_at": posting.collected_at,
        }

    def upsert_postings(self, postings: Sequence[JobPosting]) -> UpsertResult:
        """INSERT ... ON CONFLICT DO UPDATE in a single transaction.

        Mutable fields and last_seen_at are refreshed; identity and first_seen_at
        are preserved. Rolls back entirely on any failure.
        """
        # A single INSERT cannot affect the same key twice: dedupe, keeping the last.
        rows = {
            (p.source, p.board_slug, p.external_id): self._to_row(p) for p in postings
        }
        if not rows:
            return UpsertResult(0, 0)

        values = list(rows.values())
        inserted = updated = 0
        with self.engine.begin() as conn:
            for start in range(0, len(values), _CHUNK_SIZE):
                stmt = insert(JobPostingRow).values(values[start : start + _CHUNK_SIZE])
                excluded = stmt.excluded
                content_changed = JobPostingRow.content.is_distinct_from(
                    excluded.content
                )
                upsert = stmt.on_conflict_do_update(
                    constraint=UNIQUE_CONSTRAINT_NAME,
                    set_={
                        "title": excluded.title,
                        "location": excluded.location,
                        "is_remote": excluded.is_remote,
                        "country_code": excluded.country_code,
                        "url": excluded.url,
                        "updated_at": excluded.updated_at,
                        "content": excluded.content,
                        "is_data_role": excluded.is_data_role,
                        "last_seen_at": excluded.last_seen_at,
                        # An evaluation describes the text it read: drop it when
                        # the posting content changes so it is re-evaluated.
                        **{
                            field: case(
                                (content_changed, None),
                                else_=getattr(JobPostingRow, field),
                            )
                            for field in _EVALUATION_FIELDS
                        },
                    },
                ).returning(text("(xmax = 0) AS inserted"))
                for (was_inserted,) in conn.execute(upsert):
                    if was_inserted:
                        inserted += 1
                    else:
                        updated += 1
        return UpsertResult(inserted, updated)

    def fetch_unevaluated(
        self, limit: int, allowed_countries: Sequence[str]
    ) -> list[PendingPosting]:
        """Data-family postings without a score whose country hint allows us.

        Only is_data_role = TRUE is sent to the paid LLM: FALSE is out of scope
        and NULL (not classified yet) must go through `classify` first.
        NULL country_code is kept: unknown location needs review, it is not
        proof of eligibility. Postings without content have nothing to evaluate.
        """
        country = JobPostingRow.country_code
        stmt = (
            select(
                JobPostingRow.id,
                JobPostingRow.title,
                JobPostingRow.location,
                JobPostingRow.country_code,
                JobPostingRow.url,
                JobPostingRow.content,
            )
            .where(
                JobPostingRow.is_data_role.is_(True),
                JobPostingRow.match_score.is_(None),
                JobPostingRow.content.is_not(None),
                JobPostingRow.content != "",
                or_(country.is_(None), country.in_(list(allowed_countries))),
            )
            .order_by(JobPostingRow.last_seen_at.desc(), JobPostingRow.id)
            .limit(limit)
        )
        with self.engine.connect() as conn:
            return [PendingPosting(**row) for row in conn.execute(stmt).mappings()]

    def classify_unclassified(self) -> int:
        """Fill is_data_role where it is still NULL; returns rows classified.

        Writes only that column, so scores, content and timestamps of postings
        stored before migration 0004 are preserved.
        """
        select_stmt = select(JobPostingRow.id, JobPostingRow.title).where(
            JobPostingRow.is_data_role.is_(None)
        )
        with self.engine.begin() as conn:
            rows = conn.execute(select_stmt).all()
            for flag in (True, False):
                ids = [row.id for row in rows if is_data_role(row.title) is flag]
                for start in range(0, len(ids), _CHUNK_SIZE):
                    conn.execute(
                        update(JobPostingRow)
                        .where(JobPostingRow.id.in_(ids[start : start + _CHUNK_SIZE]))
                        .values(is_data_role=flag)
                    )
        return len(rows)

    def save_evaluation(
        self,
        posting_id: int,
        *,
        score: int,
        salary: str | None,
        reason: str,
        model: str,
        evaluated_at: datetime,
    ) -> bool:
        """Store one evaluation in its own transaction; False if the row is gone."""
        stmt = (
            update(JobPostingRow)
            .where(JobPostingRow.id == posting_id)
            .values(
                match_score=score,
                salary_extracted=salary,
                match_reason=reason,
                match_model=model,
                evaluated_at=evaluated_at,
            )
        )
        with self.engine.begin() as conn:
            return conn.execute(stmt).rowcount == 1
