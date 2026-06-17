"""SECURITY DEFINER resolvers for candidate-scoped application reads.

A candidate must see their own applications across ALL companies, but
`applications` has FORCE ROW LEVEL SECURITY with a company-only tenant policy, so
a least-privilege app role reads nothing without a company context (same class of
bug as the 0015–0017 resolvers). These functions return rows scoped strictly to a
single candidate_id, bypassing the company tenant policy safely.

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_LIST_APPLICATIONS = """
CREATE OR REPLACE FUNCTION candidate_list_applications(p_candidate_id uuid)
RETURNS TABLE (
    id uuid,
    job_id uuid,
    status text,
    screening_status text,
    created_at timestamptz,
    job_title text,
    company_name text
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT a.id, a.job_id, a.status, a.screening_status, a.created_at,
           j.title AS job_title, co.name AS company_name
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    LEFT JOIN companies co ON co.id = a.company_id
    WHERE a.candidate_id = p_candidate_id
    ORDER BY a.created_at DESC
$$;
"""

_APPLIED_JOB_IDS = """
CREATE OR REPLACE FUNCTION candidate_applied_job_ids(p_candidate_id uuid)
RETURNS SETOF uuid
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT job_id FROM applications WHERE candidate_id = p_candidate_id
$$;
"""


def upgrade() -> None:
    op.execute(_LIST_APPLICATIONS)
    op.execute(_APPLIED_JOB_IDS)
    op.execute("GRANT EXECUTE ON FUNCTION candidate_list_applications(uuid) TO PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION candidate_applied_job_ids(uuid) TO PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS candidate_list_applications(uuid)")
    op.execute("DROP FUNCTION IF EXISTS candidate_applied_job_ids(uuid)")
