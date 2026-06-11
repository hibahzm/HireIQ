from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="draft", nullable=False)
    streaming_interview: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    company: Mapped["Company"] = relationship("Company", back_populates="jobs", lazy="raise")
    criteria: Mapped["JobCriteria | None"] = relationship("JobCriteria", back_populates="job", uselist=False, lazy="raise")
    setup_conversation: Mapped["SetupConversation | None"] = relationship("SetupConversation", back_populates="job", uselist=False, lazy="raise")
