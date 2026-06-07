"""Create evaluations table

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-05

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("overall_score", sa.SmallInteger(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("dimension_scores", sa.JSON(), nullable=False),
        sa.Column("consistency_flags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("communication_quality", sa.JSON(), nullable=False),
        sa.Column("confidence_flag", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("confidence_reason", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("feedback_token", sa.UUID(), nullable=True),
        sa.Column("feedback_token_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "recommendation IN ('hire','no_hire','uncertain')",
            name="ck_evaluations_recommendation",
        ),
        sa.CheckConstraint("overall_score BETWEEN 0 AND 100", name="ck_evaluations_overall_score"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="uq_evaluations_application_id"),
    )

    op.create_index("ix_evaluations_company_score", "evaluations", ["company_id", sa.text("overall_score DESC")])
    op.create_index("ix_evaluations_feedback_token", "evaluations", ["feedback_token"], unique=True, postgresql_where=sa.text("feedback_token IS NOT NULL"))

    op.execute("ALTER TABLE evaluations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evaluations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON evaluations
        USING (company_id = current_setting('app.current_company_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON evaluations")
    op.drop_index("ix_evaluations_feedback_token", table_name="evaluations")
    op.drop_index("ix_evaluations_company_score", table_name="evaluations")
    op.drop_table("evaluations")
