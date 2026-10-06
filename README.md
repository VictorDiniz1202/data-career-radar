# Data Career Radar

Collect public postings from curated Greenhouse and Ashby boards, normalize basic
location hints, and persist them idempotently in PostgreSQL. Remote status is a
hint, **not proof of eligibility to work from Brazil**.

## Current scope

- Provider adapters with canonical Pydantic models.
- Raw `location` preserved alongside `is_remote` and nullable `country_code`.
- Conservative BR/US hints using country names/codes and a small city dictionary.
  Unknown or conflicting locations stay unclassified. Unrecognized place names
  also return NULL even alongside a known country: coverage favors precision.
  Secondary Ashby locations are outside this increment.
- UPSERT keyed by `(source, board_slug, external_id)`, preserving `first_seen_at`
  and refreshing mutable fields and `last_seen_at`.

Ranking, eligibility, snapshots, history, dashboards and scheduling are not
implemented. No time-saving or hiring-outcome metrics are claimed.

## Local setup

Requires Python 3.12+, Docker and Docker Compose. Run from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
Copy-Item .env.example .env
# Edit .env with your local database settings before starting PostgreSQL.
docker compose up -d db
python -m alembic upgrade head
career-radar --action ingest --source greenhouse --slug clara
career-radar --action ingest --source ashby --slug constructor
```

The default source is Greenhouse (`clara`); Ashby's default board is `constructor`.
`--limit` controls printed samples; all collected postings are stored. Re-ingest
a board to update existing location hints. Migration `0002` initializes existing
rows to `is_remote=false`, `country_code=NULL`, without a historical backfill.
The `normalize` action prints ingestion guidance; it is not a backfill command.

The Ashby adapter follows the [public API contract](https://developers.ashbyhq.com/docs/public-job-posting-api).
It reads `title`, skips explicitly unlisted postings and uses `id` when present,
otherwise the validated URL. A later change from missing to present ID may need
identity reconciliation. `publishedAt` is not an update timestamp, so `updated_at`
stays unknown. No pagination is documented. HTTP errors (including 429), timeouts
and malformed listed records fail before persistence. Retries are not implemented.

## Validation

```powershell
python -m build
python -m flake8 src tests migrations --max-line-length=88 --extend-ignore=E203,W503
python -m mypy src/career_radar --check-untyped-defs
python -m pytest -q
```

Database tests require schema creation permissions and use unique temporary
schemas. They cover migrations, existing rows, updates, country clearing,
concurrent UPSERTs and provider/board isolation.

```powershell
$env:CAREER_RADAR_TEST_DB = '1'
python -m pytest -q
python -m alembic check
```

To reverse the latest migration, use
`python -m alembic downgrade 0001_create_job_postings`. This removes the two derived
columns and keeps the posting rows; re-upgrade and re-ingest to recompute them.
Validate reversals in an isolated database/schema first.

## Known limits

Dependencies have no lockfile. The existing Compose file publishes PostgreSQL on
all interfaces; review the bind before use on shared networks. The existing
Dockerfile and a clean-clone setup have not been validated in this sprint.
Full-tree lint has one pre-existing long line in the Greenhouse adapter.
Credentials, raw dumps and personal career context stay outside version control.
