from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class JobCriteria(Base):
    __tablename__ = "job_criteria"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    required_skills: Mapped[list] = mapped_column(
        JSONB, server_default="'[]'::jsonb", nullable=False
    )
    optional_skills: Mapped[list] = mapped_column(
        JSONB, server_default="'[]'::jsonb", nullable=False
    )
    experience_level: Mapped[str] = mapped_column(Text, nullable=False)
    min_years_experience: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    evaluation_dimensions: Mapped[list] = mapped_column(JSONB, nullable=False)
    dealbreakers: Mapped[list] = mapped_column(JSONB, server_default="'[]'::jsonb", nullable=False)
    min_screening_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    job: Mapped[Job] = relationship("Job", back_populates="criteria", lazy="raise")
