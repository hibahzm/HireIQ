from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SetupConversation(Base):
    __tablename__ = "setup_conversations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    messages: Mapped[list] = mapped_column(JSONB, server_default="'[]'::jsonb", nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="in_progress", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    job: Mapped[Job] = relationship("Job", back_populates="setup_conversation", lazy="raise")
