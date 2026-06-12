"""SECURITY DEFINER resolver for public feedback-report tokens.

GET /feedback/{token} is public — the token is the authenticator and no company
context exists. Like 0015 (interview tokens) and 0016 (auth lookups), the direct
SELECT only worked when the app role was a superuser; under FORCE RLS a
least-privilege role sees nothing.
"""
from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION resolve_feedback_token(tok uuid)
RETURNS SETOF evaluations
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT * FROM evaluations WHERE feedback_token = tok LIMIT 1
$$;
"""


def upgrade() -> None:
    op.execute(_FUNCTION)
    op.execute("GRANT EXECUTE ON FUNCTION resolve_feedback_token(uuid) TO PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_feedback_token(uuid)")
