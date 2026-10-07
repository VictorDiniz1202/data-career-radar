"""SQLAlchemy declarative model and engine factory for the storage layer."""

import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    false,
)
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

UNIQUE_CONSTRAINT_NAME = "uq_job_postings_source_board_external_id"
SCORE_CHECK_CONSTRAINT_NAME = "ck_job_postings_match_score_range"


class Base(DeclarativeBase):
    pass


class JobPostingRow(Base):
    """One job ad, identified by (source, board_slug, external_id) at the provider."""

    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint(
            "source", "board_slug", "external_id", name=UNIQUE_CONSTRAINT_NAME
        ),
        CheckConstraint(
            "match_score BETWEEN 1 AND 10", name=SCORE_CHECK_CONSTRAINT_NAME
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    board_slug: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    is_remote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    country_code: Mapped[str | None] = mapped_column(String(2))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # LLM evaluation: NULL means "not evaluated yet". The score ranks review
    # effort; it is not a probability of being hired.
    # Title pre-filter: NULL means "not classified yet" (rows from before 0004),
    # so only an explicit TRUE makes a posting eligible for a paid LLM call.
    is_data_role: Mapped[bool | None] = mapped_column(Boolean)
    match_score: Mapped[int | None] = mapped_column(Integer)
    salary_extracted: Mapped[str | None] = mapped_column(Text)
    match_reason: Mapped[str | None] = mapped_column(Text)
    match_model: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def get_database_url() -> URL:
    """Build the connection URL from POSTGRES_* env vars (see .env.example).

    Uses URL.create so special characters in the password are escaped safely.
    """
    load_dotenv()
    return URL.create(
        "postgresql+psycopg2",
        username=os.environ.get("POSTGRES_USER", "radar_user"),
        password=os.environ.get("POSTGRES_PASSWORD"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        database=os.environ.get("POSTGRES_DB", "radar_db"),
    )


def get_engine() -> Engine:
    return create_engine(get_database_url(), pool_pre_ping=True)
