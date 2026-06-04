from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    applications: Mapped[list["Application"]] = relationship("Application", back_populates="candidate", lazy="raise")
