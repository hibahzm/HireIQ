"""SECURITY DEFINER lookups for pre-auth user resolution.

Login, registration duplicate-checks, token refresh, and invite set-password all
need to find a user before any company context exists — but `users` has FORCE
ROW LEVEL SECURITY with a tenant-only policy, so those SELECTs return nothing
for a least-privilege app role (they only worked in dev because the Docker role
is a superuser; same class of bug as the interview-token resolver in 0015).
"""
from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_BY_EMAIL = """
CREATE OR REPLACE FUNCTION auth_find_user_by_email(p_email text)
RETURNS SETOF users
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT * FROM users WHERE lower(email) = lower(p_email) LIMIT 1
$$;
"""

_BY_ID = """
CREATE OR REPLACE FUNCTION auth_find_user_by_id(p_id uuid)
RETURNS SETOF users
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT * FROM users WHERE id = p_id LIMIT 1
$$;
"""


def upgrade() -> None:
    op.execute(_BY_EMAIL)
    op.execute(_BY_ID)
    op.execute("GRANT EXECUTE ON FUNCTION auth_find_user_by_email(text) TO PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION auth_find_user_by_id(uuid) TO PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS auth_find_user_by_email(text)")
    op.execute("DROP FUNCTION IF EXISTS auth_find_user_by_id(uuid)")
