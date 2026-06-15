"""Fix RLS policies: use missing_ok=true + public SELECT on active jobs

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-05

Without `missing_ok=true`, PostgreSQL raises an error when
current_setting('app.current_company_id') is called and the session
variable has never been set (e.g. public endpoints, background tasks).
With `true` it returns NULL instead, which safely matches no rows.

Also adds a FOR SELECT policy on jobs so the public application endpoint
can look up an active job by ID before the company context is known.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# All tenant-scoped tables that need the fix
_TENANT_TABLES = [
    "users",
    "jobs",
    "job_criteria",
    "setup_conversations",
    "applications",
    "cv_chunks",
    "job_chunks",
    "interview_sessions",
    "interview_messages",
]

_SAFE_POLICY = (
    "company_id = current_setting('app.current_company_id', true)::uuid"
    " AND current_setting('app.current_company_id', true) IS NOT NULL"
)


def upgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} " f"USING ({_SAFE_POLICY})")

    # Public SELECT: candidates can look up active jobs for the application form
    # without knowing the company_id ahead of time.
    op.execute(
        "CREATE POLICY public_read_active_jobs ON jobs " "FOR SELECT " "USING (status = 'active')"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS public_read_active_jobs ON jobs")

    _ORIGINAL = "company_id = current_setting('app.current_company_id')::uuid"
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} " f"USING ({_ORIGINAL})")
