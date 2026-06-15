"""Allow 'failed' as a terminal screening_status

The screening pipeline runs as a background task; when it crashes we need a
terminal state to mark the application so it isn't stuck in 'pending' forever.
The original CHECK only permitted ('pending','qualified','rejected'), so add
'failed'.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_applications_screening_status"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "applications", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "applications",
        "screening_status IN ('pending','qualified','rejected','failed')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "applications", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "applications",
        "screening_status IN ('pending','qualified','rejected')",
    )
