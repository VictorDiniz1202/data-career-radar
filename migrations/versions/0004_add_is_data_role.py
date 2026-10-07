"""Add nullable is_data_role flag; NULL means "not classified yet".

Existing rows are left untouched (NULL); `career-radar --action classify`
fills them in without modifying any other column.

Revision ID: 0004_add_is_data_role
Revises: 0003_add_llm_evaluation_fields
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_add_is_data_role"
down_revision = "0003_add_llm_evaluation_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_postings", sa.Column("is_data_role", sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("job_postings", "is_data_role")
