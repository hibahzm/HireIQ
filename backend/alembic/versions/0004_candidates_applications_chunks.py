"""Create candidates, applications, cv_chunks, job_chunks tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-04

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # candidates — global, no RLS
    op.create_table(
        "candidates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_candidates_email"),
    )

    # applications
    op.create_table(
        "applications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("cv_blob_key", sa.Text(), nullable=False),
        sa.Column("cv_text", sa.Text(), nullable=True),
        sa.Column("cv_extraction_method", sa.Text(), nullable=True),
        sa.Column("screening_score", sa.SmallInteger(), nullable=True),
        sa.Column("screening_rationale", sa.Text(), nullable=True),
        sa.Column("screening_status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("interview_token", sa.UUID(), nullable=True),
        sa.Column("interview_token_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default="applied", nullable=False),
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
        sa.CheckConstraint(
            "screening_status IN ('pending','qualified','rejected')",
            name="ck_applications_screening_status",
        ),
        sa.CheckConstraint(
            "status IN ('applied','screening','qualified','rejected','invited','interviewing','evaluated','archived')",
            name="ck_applications_status",
        ),
        sa.CheckConstraint("screening_score BETWEEN 0 AND 100", name="ck_applications_score"),
        sa.CheckConstraint(
            "cv_extraction_method IN ('pymupdf','document_intelligence')",
            name="ck_applications_extraction",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "candidate_id", name="uq_applications_job_candidate"),
    )
    op.create_index(
        "ix_applications_job_screening_status", "applications", ["job_id", "screening_status"]
    )
    op.create_index(
        "ix_applications_interview_token", "applications", ["interview_token"], unique=True
    )

    op.execute("ALTER TABLE applications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE applications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON applications
        USING (company_id = current_setting('app.current_company_id')::uuid)
        """
    )

    # cv_chunks — needs pgvector
    op.create_table(
        "cv_chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.SmallInteger(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),  # stored as text, cast via pgvector
        sa.Column("tsv", postgresql.TSVECTOR(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Use raw SQL for vector column type and generated tsvector column
    op.execute(
        "ALTER TABLE cv_chunks ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    op.execute("ALTER TABLE cv_chunks ALTER COLUMN tsv DROP NOT NULL")
    op.execute("ALTER TABLE cv_chunks ALTER COLUMN tsv SET DEFAULT to_tsvector('english', '')")
    op.execute(
        "CREATE INDEX ix_cv_chunks_embedding ON cv_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
    )
    op.execute("CREATE INDEX ix_cv_chunks_tsv ON cv_chunks USING GIN (tsv)")

    op.execute("ALTER TABLE cv_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cv_chunks FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON cv_chunks
        USING (company_id = current_setting('app.current_company_id')::uuid)
        """
    )

    # job_chunks
    op.create_table(
        "job_chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.SmallInteger(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "ALTER TABLE job_chunks ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    op.execute(
        "CREATE INDEX ix_job_chunks_embedding ON job_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists=50)"
    )

    op.execute("ALTER TABLE job_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE job_chunks FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON job_chunks
        USING (company_id = current_setting('app.current_company_id')::uuid)
        """
    )


def downgrade() -> None:
    for table in ("cv_chunks", "job_chunks", "applications"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("job_chunks")
    op.drop_table("cv_chunks")
    op.drop_table("applications")
    op.drop_table("candidates")
