from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class InterviewMessage(Base):
    __tablename__ = "interview_messages"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    speaker: Mapped[str] = mapped_column(Text, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_blob_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession", back_populates="messages", lazy="raise"
    )
