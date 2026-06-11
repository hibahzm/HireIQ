from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    application_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True)
    company_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    streaming_mode: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    turn_count: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    max_turns: Mapped[int] = mapped_column(SmallInteger, server_default="6", nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    messages: Mapped[list["InterviewMessage"]] = relationship("InterviewMessage", back_populates="session", lazy="raise", order_by="InterviewMessage.turn_index")
