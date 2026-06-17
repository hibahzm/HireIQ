from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CandidateCv(Base):
    """One whole-CV row per candidate (global, no RLS).

    Unlike `cv_chunks` (per-application, chunked, company-scoped), this stores the
    candidate's single current CV as ONE pgvector embedding plus a structured
    `skills` record and a full-text `tsv`, for cross-company sourcing search.
    """

    __tablename__ = "candidate_cvs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    candidate_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    cv_blob_key: Mapped[str] = mapped_column(Text, nullable=False)
    cv_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_extraction_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Embedding stored as pgvector type — use Text at ORM level, cast in queries.
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{skill, years, years_basis, evidence}] — populated by the Phase 2 extractor.
    skills: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    embedding_truncated: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
