from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CvChunk(Base):
    __tablename__ = "cv_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    application_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Embedding stored as pgvector type — use Text at ORM level, cast in queries
    embedding: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
