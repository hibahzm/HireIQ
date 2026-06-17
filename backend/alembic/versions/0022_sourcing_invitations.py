"""Sourcing invitations: a company's offer to a sourced candidate for a job.

Global table (no RLS), like `candidates`/`candidate_cvs`, because a candidate must
read invitations across companies. Access is enforced in the app layer: company
endpoints filter by company_id, candidate endpoints by candidate_id. On acceptance
the invitation becomes a deduplicated application via the normal apply path.

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sourcing_invitations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','expired')",
            name="ck_sourcing_invitations_status",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "candidate_id", name="uq_sourcing_invitations_job_candidate"),
    )
    op.create_index(
        "ix_sourcing_invitations_candidate", "sourcing_invitations", ["candidate_id", "status"]
    )
    op.create_index(
        "ix_sourcing_invitations_company", "sourcing_invitations", ["company_id", "job_id"]
    )
    # Global (no RLS) — access is enforced in the application layer.


def downgrade() -> None:
    op.drop_table("sourcing_invitations")
