from __future__ import annotations

from collections.abc import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.ENV == "development",
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def get_db(company_id: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession with RLS context set.
    company_id must be provided for all tenant-scoped queries.
    """
    async with _get_session_factory()() as session:
        async with session.begin():
            if company_id:
                await session.execute(
                    sa.text("SET LOCAL app.current_company_id = :cid"),
                    {"cid": str(company_id)},
                )
            yield session
