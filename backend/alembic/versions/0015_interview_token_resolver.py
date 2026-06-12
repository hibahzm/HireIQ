"""Interview-token resolver that works under RLS.

The candidate joins the interview with only their token — before any company
context exists. `applications` has FORCE ROW LEVEL SECURITY with a tenant-only
policy, so a plain SELECT by token returns nothing for a least-privilege app
role (it only ever worked in dev because the Docker role is a superuser).

This SECURITY DEFINER function (owned by the migration/admin role) resolves a
token to its application/company so the app can then set the RLS context and
proceed with normally-scoped queries. It exposes nothing beyond what the token
itself authorizes.
"""
from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION resolve_interview_application(tok uuid)
RETURNS TABLE (
    application_id uuid,
    company_id uuid,
    job_id uuid,
    streaming_interview boolean
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT a.id, a.company_id, a.job_id, COALESCE(j.streaming_interview, false)
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    WHERE a.interview_token = tok
      AND a.interview_token_expires_at > now()
$$;
"""


def upgrade() -> None:
    op.execute(_FUNCTION)
    op.execute("GRANT EXECUTE ON FUNCTION resolve_interview_application(uuid) TO PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_interview_application(uuid)")
