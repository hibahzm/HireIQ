"""Create interview_sessions and interview_messages tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-04

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # interview_sessions
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("turn_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("max_turns", sa.SmallInteger(), server_default="20", nullable=False),
        sa.Column("last_active_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mode IN ('voice','text')", name="ck_interview_sessions_mode"),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','completed','expired','system_interrupted','abandoned')",
            name="ck_interview_sessions_status",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="uq_interview_sessions_application_id"),
    )

    op.execute("ALTER TABLE interview_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE interview_sessions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON interview_sessions
        USING (company_id = current_setting('app.current_company_id')::uuid)
        """
    )

    # interview_messages
    op.create_table(
        "interview_messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("turn_index", sa.SmallInteger(), nullable=False),
        sa.Column("speaker", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("audio_blob_key", sa.Text(), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("speaker IN ('candidate','ai')", name="ck_interview_messages_speaker"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "turn_index", name="uq_interview_messages_session_turn"),
    )

    op.execute("ALTER TABLE interview_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE interview_messages FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON interview_messages
        USING (company_id = current_setting('app.current_company_id')::uuid)
        """
    )


def downgrade() -> None:
    for table in ("interview_messages", "interview_sessions"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("interview_messages")
    op.drop_table("interview_sessions")
