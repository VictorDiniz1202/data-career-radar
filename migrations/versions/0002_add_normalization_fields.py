"""Add location hints; existing rows are normalized on their next ingestion.

Revision ID: 0002_add_normalization_fields
Revises: 0001_create_job_postings
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_normalization_fields"
down_revision = "0001_create_job_postings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("is_remote", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "job_postings", sa.Column("country_code", sa.String(2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("job_postings", "country_code")
    op.drop_column("job_postings", "is_remote")
