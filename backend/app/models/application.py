from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("candidates.id"), nullable=False)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    cv_blob_key: Mapped[str] = mapped_column(Text, nullable=False)
    cv_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_extraction_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    screening_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    screening_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    screening_status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    interview_token: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    interview_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="applied", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="applications", lazy="raise")
