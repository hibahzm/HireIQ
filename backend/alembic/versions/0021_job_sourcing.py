"""Per-job in-app sourcing toggle.

A company can keep the external application link AND/OR enable in-app sourcing
(proactively searching the candidate pool) per job. Defaults off so existing
jobs are unchanged.

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "sourcing_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "sourcing_enabled")
