from __future__ import annotations

from collections.abc import AsyncGenerator

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _get_session_factory
from app.models.user import User
from app.repositories.user_repository import UserRepository

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """
    Decode the Bearer JWT and return the authenticated User.
    Opens its own short-lived session (just for the user lookup), then closes it.
    No session is held open — routes get their session from get_authed_session.
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id: str = payload["sub"]
    company_id: str = payload["company_id"]
    request.state.company_id = company_id

    async with _get_session_factory()() as session:
        async with session.begin():
            await session.execute(
                sa.text("SET LOCAL app.current_company_id = :cid"),
                {"cid": company_id},
            )
            user = await UserRepository(session).get_by_id(user_id)
            if not user or not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive",
                )
            return user


async def get_authed_session(
    current_user: User = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession with RLS already set to the authenticated user's company.

    FastAPI deduplicates dependencies per request — get_current_user runs only once
    even when both Depends(require_recruiter_or_admin) and Depends(get_authed_session)
    appear in the same route signature.

    Usage in routes:
        session: AsyncSession = Depends(get_authed_session)
    """
    async with _get_session_factory()() as session:
        async with session.begin():
            await session.execute(
                sa.text("SET LOCAL app.current_company_id = :cid"),
                {"cid": str(current_user.company_id)},
            )
            yield session


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user


async def require_recruiter_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "recruiter"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter or admin required",
        )
    return current_user
