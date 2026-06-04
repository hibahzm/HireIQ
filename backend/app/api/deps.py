from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthError, AuthService

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db=Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    from app.redis_client import get_redis
    from app.config import get_settings

    settings = get_settings()

    # Decode token (no DB call needed for validation)
    async for r in get_redis():
        svc = AuthService.__new__(AuthService)
        svc._settings = settings
        svc._redis = r
        svc._session = None

        try:
            payload = svc.decode_access_token(credentials.credentials)
        except AuthError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id: str = payload["sub"]
    company_id: str = payload["company_id"]

    # Set company_id on request state so logging middleware can pick it up
    request.state.company_id = company_id

    # Load user from DB with RLS set
    async for session in get_db(company_id=company_id):
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user


async def require_recruiter_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "recruiter"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter or admin required")
    return current_user
