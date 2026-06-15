"""Default new jobs to streaming interviews.

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-11

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "jobs",
        "streaming_interview",
        server_default=sa.text("true"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.execute("UPDATE jobs SET streaming_interview = true WHERE streaming_interview = false")


def downgrade() -> None:
    op.alter_column(
        "jobs",
        "streaming_interview",
        server_default=sa.text("false"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
