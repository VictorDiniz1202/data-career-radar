"""Evaluate stored, not-yet-scored postings against a resume read from disk."""

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Sequence

from career_radar.analysis.llm_client import EvaluationResponse, LLMError
from career_radar.storage.repository import JobPostingRepository, PendingPosting

# Hard ceiling per run, whatever --limit says: every evaluation is a paid call.
MAX_EVALUATIONS_PER_RUN = 20
MAX_RESUME_BYTES = 50_000
MAX_POSTING_CHARS = 15_000
RESUME_SUFFIXES = {".md", ".txt"}

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TAG = re.compile(r"<[^>]+>")
_BLANK = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class ResumeError(Exception):
    """The resume file is missing, unsupported, too large or inside the repo."""


class Evaluator(Protocol):
    def evaluate(self, resume: str, posting: str) -> EvaluationResponse: ...


@dataclass(frozen=True)
class EvaluationOutcome:
    posting: PendingPosting
    response: EvaluationResponse | None = None
    error: str | None = None


def load_resume(path: Path) -> str:
    """Read a local .md/.txt resume kept outside the repository."""
    resolved = path.expanduser().resolve()
    # Only enforced from a source checkout; an installed wheel has no repo root.
    if (_PROJECT_ROOT / "pyproject.toml").is_file() and resolved.is_relative_to(
        _PROJECT_ROOT
    ):
        raise ResumeError("keep the resume outside the repository")
    if resolved.suffix.lower() not in RESUME_SUFFIXES:
        raise ResumeError("resume must be a .md or .txt file")
    if not resolved.is_file():
        raise ResumeError("resume file not found")
    if resolved.stat().st_size > MAX_RESUME_BYTES:
        raise ResumeError(f"resume larger than {MAX_RESUME_BYTES} bytes")
    text = resolved.read_text(encoding="utf-8").strip()
    if not text:
        raise ResumeError("resume file is empty")
    return text


def posting_to_text(posting: PendingPosting) -> str:
    """Plain text for the model: unescaped, tag-free and bounded in size."""
    body = _TAG.sub(" ", html.unescape(html.unescape(posting.content)))
    body = _BLANK_LINES.sub("\n\n", _BLANK.sub(" ", body)).strip()
    return (
        f"Title: {posting.title}\n"
        f"Location: {posting.location or 'not stated'}\n\n"
        f"{body[:MAX_POSTING_CHARS]}"
    )


def evaluate_pending(
    repository: JobPostingRepository,
    client: Evaluator,
    resume: str,
    limit: int,
    allowed_countries: Sequence[str],
) -> list[EvaluationOutcome]:
    """Score up to `limit` pending postings, persisting each one as it succeeds.

    A failed call is reported and left NULL so the next run retries it.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    batch = min(limit, MAX_EVALUATIONS_PER_RUN)
    outcomes = []
    for posting in repository.fetch_unevaluated(batch, allowed_countries):
        try:
            response = client.evaluate(resume, posting_to_text(posting))
        except LLMError as exc:
            outcomes.append(EvaluationOutcome(posting, error=str(exc)))
            continue
        evaluation = response.evaluation
        stored = repository.save_evaluation(
            posting.id,
            score=evaluation.score,
            salary=evaluation.salary_or_none,
            reason=evaluation.reason,
            model=response.model,
            evaluated_at=datetime.now(timezone.utc),
        )
        outcomes.append(
            EvaluationOutcome(
                posting, response, None if stored else "posting no longer stored"
            )
        )
    return outcomes
