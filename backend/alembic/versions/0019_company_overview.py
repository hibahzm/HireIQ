"""companies.overview — recruiter-written company blurb.

Sila (the AI interviewer) answers candidate questions about the company using
ONLY this text; questions it doesn't cover get a polite "I'll pass that to the
hiring team" instead of hallucinated facts.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("overview", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "overview")
