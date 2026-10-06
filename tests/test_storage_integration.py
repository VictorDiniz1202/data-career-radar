"""Opt-in PostgreSQL checks, isolated in a unique disposable schema."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from career_radar.ingestion.models import JobPosting
from career_radar.storage.database import JobPostingRow, get_engine
from career_radar.storage.repository import JobPostingRepository

pytestmark = pytest.mark.skipif(
    os.environ.get("CAREER_RADAR_TEST_DB") != "1",
    reason="Set CAREER_RADAR_TEST_DB=1 with POSTGRES_* to test an isolated schema",
)


@pytest.fixture
def database(monkeypatch):
    schema = "sprint3_test_" + uuid4().hex
    admin = get_engine()
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    monkeypatch.setenv("PGOPTIONS", f"-csearch_path={schema}")
    engine = get_engine()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        yield engine, config
    finally:
        command.downgrade(config, "base")
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}"'))
        admin.dispose()


def posting(location="Remote U.S.", **changes):
    return JobPosting(
        **{
            "source": "ashby",
            "board_slug": "example",
            "external_id": "test-job",
            "title": "Data Engineer",
            "url": "https://example.com/job",
            "location": location,
            **changes,
        }
    )


def test_upgrade_existing_data_upsert_and_downgrade(database):
    engine, config = database
    command.upgrade(config, "0001_create_job_postings")
    observed = datetime(2026, 10, 6, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO job_postings
            (source, board_slug, external_id, title, location, url,
             first_seen_at, last_seen_at)
            VALUES ('ashby', 'example', 'test-job', 'Old title',
                    'Remote U.S.', 'https://example.com/job', :seen, :seen)
        """),
            {"seen": observed},
        )
    command.upgrade(config, "head")
    with engine.connect() as conn:
        before = conn.execute(select(JobPostingRow.__table__)).mappings().one()
        assert before["is_remote"] is False
        assert before["country_code"] is None
    repository = JobPostingRepository(engine)
    result = repository.upsert_postings(
        [posting(collected_at=observed + timedelta(hours=1))]
    )
    assert (result.inserted, result.updated) == (0, 1)
    with engine.connect() as conn:
        row = conn.execute(select(JobPostingRow.__table__)).mappings().one()
        assert (row["is_remote"], row["country_code"]) == (True, "US")
        assert row["first_seen_at"] == observed
        assert row["last_seen_at"] > observed
    repository.upsert_postings([posting("São Paulo / SP / Brazil")])
    with engine.connect() as conn:
        row = conn.execute(select(JobPostingRow.__table__)).mappings().one()
        assert (row["is_remote"], row["country_code"]) == (False, "BR")
    repository.upsert_postings([posting("Unknown")])
    with engine.connect() as conn:
        row = conn.execute(select(JobPostingRow.__table__)).mappings().one()
        assert row["country_code"] is None
    command.check(config)
    command.downgrade(config, "0001_create_job_postings")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM job_postings")).scalar_one() == 1
        assert (
            "is_remote" not in conn.execute(text("SELECT * FROM job_postings")).keys()
        )
    command.upgrade(config, "head")
    command.check(config)


def test_concurrent_upserts_and_provider_isolation(database):
    engine, config = database
    command.upgrade(config, "head")
    repository = JobPostingRepository(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: repository.upsert_postings([posting()]), range(2))
        )
    assert sum(r.inserted for r in results) == 1
    assert sum(r.updated for r in results) == 1
    assert repository.upsert_postings([posting(source="greenhouse")]).inserted == 1
    assert repository.upsert_postings([posting(board_slug="other")]).inserted == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM job_postings")).scalar_one() == 3
