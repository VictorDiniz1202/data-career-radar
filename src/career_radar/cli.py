import argparse
import sys

from sqlalchemy.exc import SQLAlchemyError

from career_radar.ingestion.greenhouse_adapter import GreenhouseAdapter, GreenhouseError
from career_radar.storage.database import get_engine
from career_radar.storage.repository import JobPostingRepository

DEFAULT_SLUG = "clara"


def run_ingest(slug: str, limit: int) -> int:
    """Fetch a Greenhouse board, print a sample, and upsert it into PostgreSQL."""
    try:
        board = GreenhouseAdapter().fetch_board(slug)
    except GreenhouseError as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1

    print(f"{board.source}/{board.board_slug}: {len(board.postings)} postings fetched")
    for posting in board.postings[:limit]:
        print(f"- title: {posting.title}")
        print(f"  location: {posting.location}")
        print(f"  url: {posting.url}")

    try:
        result = JobPostingRepository(get_engine()).upsert_postings(board.postings)
    except SQLAlchemyError as exc:
        # Do not echo the full error: it may contain connection details.
        print(f"Storage failed ({type(exc).__name__}); transaction rolled back.", file=sys.stderr)
        return 1

    print(f"Stored: {result.inserted} new, {result.updated} updated ({result.total} total)")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Data Career Radar CLI")
    parser.add_argument("--action", choices=["ingest", "normalize"], help="Action to perform")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="Greenhouse board slug")
    parser.add_argument("--limit", type=int, default=5, help="Max postings to print")

    args = parser.parse_args()

    if args.action == "ingest":
        sys.exit(run_ingest(args.slug, args.limit))
    elif args.action == "normalize":
        print("Normalization not implemented yet.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
