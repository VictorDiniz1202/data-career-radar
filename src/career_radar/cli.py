import argparse
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from career_radar.analysis.evaluator import (
    MAX_EVALUATIONS_PER_RUN,
    ResumeError,
    evaluate_pending,
    load_resume,
)
from career_radar.analysis.llm_client import GeminiClient, LLMError
from career_radar.ingestion.ashby_adapter import AshbyAdapter, AshbyError
from career_radar.ingestion.greenhouse_adapter import GreenhouseAdapter, GreenhouseError
from career_radar.storage.database import get_engine
from career_radar.storage.repository import JobPostingRepository

DEFAULT_SLUG = "clara"


def run_ingest(slug: str, limit: int, source: str = "greenhouse") -> int:
    """Fetch a supported board, print a sample, and upsert it into PostgreSQL."""
    try:
        adapter = AshbyAdapter() if source == "ashby" else GreenhouseAdapter()
        board = adapter.fetch_board(slug)
    except (GreenhouseError, AshbyError) as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1

    print(f"{board.source}/{board.board_slug}: {len(board.postings)} postings fetched")
    for posting in board.postings[:limit]:
        print(f"- title: {posting.title}")
        print(f"  location: {posting.location}")
        print(f"  remote: {posting.is_remote}; country: {posting.country_code}")
        print(f"  url: {posting.url}")

    try:
        result = JobPostingRepository(get_engine()).upsert_postings(board.postings)
    except SQLAlchemyError as exc:
        # Do not echo the full error: it may contain connection details.
        print(
            f"Storage failed ({type(exc).__name__}); transaction rolled back.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Stored: {result.inserted} new, {result.updated} updated "
        f"({result.total} total)"
    )
    return 0


def run_evaluate(resume_path: Path, limit: int, allowed_countries: list[str]) -> int:
    """Score up to `limit` pending postings with Gemini and print the results."""
    if limit < 1:
        print("--limit must be at least 1 for evaluate.", file=sys.stderr)
        return 2
    try:
        resume = load_resume(resume_path)
        client = GeminiClient.from_env()
    except (ResumeError, LLMError) as exc:
        print(f"Evaluation not started: {exc}", file=sys.stderr)
        return 1
    if limit > MAX_EVALUATIONS_PER_RUN:
        print(f"--limit capped at {MAX_EVALUATIONS_PER_RUN} evaluations per run.")

    try:
        outcomes = evaluate_pending(
            JobPostingRepository(get_engine()), client, resume, limit, allowed_countries
        )
    except SQLAlchemyError as exc:
        print(f"Storage failed ({type(exc).__name__}).", file=sys.stderr)
        return 1

    failures = 0
    for outcome in outcomes:
        posting = outcome.posting
        print(f"- [{posting.id}] {posting.title} ({posting.location or 'no location'})")
        if outcome.error or outcome.response is None:
            failures += 1
            print(f"  FAILED: {outcome.error}")
            continue
        evaluation = outcome.response.evaluation
        print(f"  score: {evaluation.score}/10  model: {outcome.response.model}")
        print(f"  salary: {evaluation.salary_or_none or 'not stated'}")
        print(f"  reason: {evaluation.reason}")
    print(f"Evaluated: {len(outcomes) - failures} stored, {failures} failed")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="Data Career Radar CLI")
    parser.add_argument(
        "--action",
        choices=["ingest", "normalize", "evaluate"],
        help="Action to perform",
    )
    parser.add_argument(
        "--source", choices=["greenhouse", "ashby"], default="greenhouse"
    )
    parser.add_argument("--slug", help="Company board slug (default depends on source)")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="ingest: max postings to print; evaluate: max postings to score",
    )
    parser.add_argument(
        "--resume-path",
        "--profile-path",
        dest="resume_path",
        type=Path,
        help="evaluate: local .md/.txt resume or skills inventory (outside the repo)",
    )
    parser.add_argument(
        "--allowed-countries",
        default="BR",
        help="evaluate: comma-separated country codes kept besides unknown (NULL)",
    )

    args = parser.parse_args()

    if args.action == "ingest":
        slug = args.slug or ("constructor" if args.source == "ashby" else DEFAULT_SLUG)
        sys.exit(run_ingest(slug, args.limit, args.source))
    elif args.action == "normalize":
        print(
            "Normalization runs during ingest; re-ingest a board to refresh its hints."
        )
    elif args.action == "evaluate":
        if args.resume_path is None:
            parser.error("--action evaluate requires --resume-path")
        countries = [
            code.strip().upper()
            for code in args.allowed_countries.split(",")
            if code.strip()
        ]
        sys.exit(run_evaluate(args.resume_path, args.limit, countries))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
