"""Shorten voice interview turn limit.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-11

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "interview_sessions",
        "max_turns",
        server_default=sa.text("6"),
        existing_type=sa.SmallInteger(),
        existing_nullable=False,
    )
    op.execute(
        """
        UPDATE interview_sessions
        SET max_turns = 6,
            updated_at = now()
        WHERE max_turns > 6
          AND status IN ('pending', 'in_progress', 'system_interrupted')
        """
    )


def downgrade() -> None:
    op.alter_column(
        "interview_sessions",
        "max_turns",
        server_default=sa.text("20"),
        existing_type=sa.SmallInteger(),
        existing_nullable=False,
    )
