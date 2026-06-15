"""Add streaming voice interview flags (V2-3)

- interview_sessions.streaming_mode: per-session streaming switch (default off)
- jobs.streaming_interview: job-level toggle that seeds a session's streaming_mode

Both additive with server defaults — existing rows and turn-based sessions are unaffected.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "streaming_interview",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "interview_sessions",
        sa.Column(
            "streaming_mode",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "streaming_mode")
    op.drop_column("jobs", "streaming_interview")
