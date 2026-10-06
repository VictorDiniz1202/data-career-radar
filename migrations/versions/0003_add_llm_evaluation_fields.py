"""Add nullable LLM evaluation fields; NULL score means "not evaluated yet".

Revision ID: 0003_add_llm_evaluation_fields
Revises: 0002_add_normalization_fields
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_llm_evaluation_fields"
down_revision = "0002_add_normalization_fields"
branch_labels = None
depends_on = None

SCORE_CHECK = "ck_job_postings_match_score_range"


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("match_score", sa.Integer(), nullable=True))
    op.add_column(
        "job_postings", sa.Column("salary_extracted", sa.Text(), nullable=True)
    )
    op.add_column("job_postings", sa.Column("match_reason", sa.Text(), nullable=True))
    op.add_column("job_postings", sa.Column("match_model", sa.Text(), nullable=True))
    op.add_column(
        "job_postings",
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        SCORE_CHECK, "job_postings", "match_score BETWEEN 1 AND 10"
    )


def downgrade() -> None:
    op.drop_constraint(SCORE_CHECK, "job_postings", type_="check")
    op.drop_column("job_postings", "evaluated_at")
    op.drop_column("job_postings", "match_model")
    op.drop_column("job_postings", "match_reason")
    op.drop_column("job_postings", "salary_extracted")
    op.drop_column("job_postings", "match_score")
