"""Enrich candidate application resolver with interview + feedback tokens.

The candidate portal must surface, per application: an active interview-invite link
(`applications.interview_token`) and the evaluation feedback report
(`evaluations.feedback_token`). Extends the 0023 SECURITY DEFINER resolver to
return these, still scoped strictly to one candidate_id.

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

_NEW = """
CREATE OR REPLACE FUNCTION candidate_list_applications(p_candidate_id uuid)
RETURNS TABLE (
    id uuid,
    job_id uuid,
    status text,
    screening_status text,
    created_at timestamptz,
    job_title text,
    company_name text,
    interview_token uuid,
    interview_token_expires_at timestamptz,
    feedback_token uuid,
    overall_score smallint
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT a.id, a.job_id, a.status, a.screening_status, a.created_at,
           j.title AS job_title, co.name AS company_name,
           a.interview_token, a.interview_token_expires_at,
           e.feedback_token, e.overall_score
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    LEFT JOIN companies co ON co.id = a.company_id
    LEFT JOIN evaluations e ON e.application_id = a.id
    WHERE a.candidate_id = p_candidate_id
    ORDER BY a.created_at DESC
$$;
"""

_OLD = """
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


def upgrade() -> None:
    # Return type changed → must drop before recreate.
    op.execute("DROP FUNCTION IF EXISTS candidate_list_applications(uuid)")
    op.execute(_NEW)
    op.execute("GRANT EXECUTE ON FUNCTION candidate_list_applications(uuid) TO PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS candidate_list_applications(uuid)")
    op.execute(_OLD)
    op.execute("GRANT EXECUTE ON FUNCTION candidate_list_applications(uuid) TO PUBLIC")
