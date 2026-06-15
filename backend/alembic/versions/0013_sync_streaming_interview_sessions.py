"""Sync existing interview sessions to realtime jobs.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-11

"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE interview_sessions s
        SET streaming_mode = true,
            updated_at = now()
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        WHERE s.application_id = a.id
          AND j.streaming_interview = true
          AND s.streaming_mode = false
        """
    )


def downgrade() -> None:
    pass
