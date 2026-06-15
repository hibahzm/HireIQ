"""Add jobs.description (recruiter-provided job/project description)

The description is captured at job creation and seeds the AI setup agent's
first turn so it can pre-extract criteria and only ask about genuine gaps.

Additive and nullable — existing rows are unaffected.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "description")
