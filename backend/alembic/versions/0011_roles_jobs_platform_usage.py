"""Add manager role, job lifecycle states, and platform usage table.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-11

"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

PLATFORM_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
PLATFORM_MANAGER_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_MANAGER_EMAIL = "manager@hireiq.local"
DEFAULT_MANAGER_PASSWORD = "Manager123!"


def _seed_platform_manager() -> None:
    """Seed the first platform manager account for local/dev bootstrap."""
    password = os.getenv("PLATFORM_MANAGER_PASSWORD")
    if os.getenv("ENV") == "production" and not password:
        return

    import bcrypt

    email = os.getenv("PLATFORM_MANAGER_EMAIL", DEFAULT_MANAGER_EMAIL).strip().lower()
    password_hash = bcrypt.hashpw(
        (password or DEFAULT_MANAGER_PASSWORD).encode(),
        bcrypt.gensalt(),
    ).decode()
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO companies (id, name)
            VALUES (:id, :name)
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
                updated_at = now()
            """
        ),
        {"id": PLATFORM_COMPANY_ID, "name": "HireIQ Platform"},
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO users (id, company_id, email, password_hash, role, is_active)
            VALUES (:id, :company_id, :email, :password_hash, 'manager', true)
            ON CONFLICT (email) DO UPDATE
            SET company_id = EXCLUDED.company_id,
                password_hash = EXCLUDED.password_hash,
                role = 'manager',
                is_active = true,
                updated_at = now()
            """
        ),
        {
            "id": PLATFORM_MANAGER_ID,
            "company_id": PLATFORM_COMPANY_ID,
            "email": email,
            "password_hash": password_hash,
        },
    )


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin', 'recruiter', 'manager')",
    )

    op.drop_constraint("ck_jobs_status", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_status",
        "jobs",
        "status IN ('draft','setup','setup_failed','active','paused','closed','archived')",
    )

    op.drop_constraint("ck_setup_conversations_status", "setup_conversations", type_="check")
    op.create_check_constraint(
        "ck_setup_conversations_status",
        "setup_conversations",
        "status IN ('in_progress','completed','failed')",
    )

    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=True),
        sa.Column("agent_type", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_usage_company_created", "llm_usage_events", ["company_id", "created_at"]
    )
    op.create_index("ix_llm_usage_agent_type", "llm_usage_events", ["agent_type"])

    _seed_platform_manager()


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": PLATFORM_MANAGER_ID})
    connection.execute(
        sa.text(
            """
            DELETE FROM companies
            WHERE id = :id
            AND NOT EXISTS (
                SELECT 1 FROM users WHERE users.company_id = companies.id
            )
            """
        ),
        {"id": PLATFORM_COMPANY_ID},
    )

    op.drop_index("ix_llm_usage_agent_type", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_company_created", table_name="llm_usage_events")
    op.drop_table("llm_usage_events")

    op.drop_constraint("ck_setup_conversations_status", "setup_conversations", type_="check")
    op.create_check_constraint(
        "ck_setup_conversations_status",
        "setup_conversations",
        "status IN ('in_progress','completed')",
    )

    op.drop_constraint("ck_jobs_status", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_status",
        "jobs",
        "status IN ('draft','setup','active','paused','closed')",
    )

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin', 'recruiter')",
    )
