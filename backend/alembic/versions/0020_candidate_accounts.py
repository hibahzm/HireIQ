"""Candidate accounts + single whole-CV index.

Extends the global, no-RLS `candidates` table with auth columns and an
`open_to_work` consent flag (so an existing apply-only record can be "upgraded"
to a real account without breaking the one-email-one-identity invariant), and
adds a global `candidate_cvs` table holding ONE whole-CV row per candidate:
a single pgvector embedding (not chunked), a structured skills JSONB, and a
full-text tsv for hybrid sourcing search. Both tables stay global (no RLS);
cross-company visibility is gated in the app layer to `open_to_work = true`.

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── candidates: auth + availability (table stays global, no RLS) ──────────
    op.add_column("candidates", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "candidates",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "candidates",
        sa.Column("open_to_work", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ── candidate_cvs: one whole-CV row per candidate (global, no RLS) ────────
    op.create_table(
        "candidate_cvs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("cv_blob_key", sa.Text(), nullable=False),
        sa.Column("cv_text", sa.Text(), nullable=True),
        sa.Column("cv_extraction_method", sa.Text(), nullable=True),
        # Embedding stored as text at create time, altered to vector(1536) below.
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column(
            "skills",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("tsv", postgresql.TSVECTOR(), nullable=True),
        sa.Column(
            "embedding_truncated",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", name="uq_candidate_cvs_candidate"),
    )
    # pgvector column + full-text default (mirrors cv_chunks DDL in 0004).
    op.execute(
        "ALTER TABLE candidate_cvs ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    op.execute("ALTER TABLE candidate_cvs ALTER COLUMN tsv SET DEFAULT to_tsvector('english', '')")
    op.execute(
        "CREATE INDEX ix_candidate_cvs_embedding ON candidate_cvs "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
    )
    op.execute("CREATE INDEX ix_candidate_cvs_tsv ON candidate_cvs USING GIN (tsv)")
    # candidate_cvs is intentionally global (no RLS): sourcing is cross-company.


def downgrade() -> None:
    op.drop_table("candidate_cvs")
    op.drop_column("candidates", "updated_at")
    op.drop_column("candidates", "open_to_work")
    op.drop_column("candidates", "is_active")
    op.drop_column("candidates", "password_hash")
