from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    application_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    overall_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_scores: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    consistency_flags: Mapped[list[Any]] = mapped_column(JSON, server_default="[]", nullable=False)
    communication_quality: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence_flag: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    confidence_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_token: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    feedback_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
