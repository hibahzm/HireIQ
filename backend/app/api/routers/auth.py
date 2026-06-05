from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from redis.asyncio import Redis

from app.api.deps import get_current_user
from app.db import _get_session_factory
from app.redis_client import get_redis
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.auth import LoginRequest, RegisterRequest, SetPasswordRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=COOKIE_MAX_AGE,
        path="/auth",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    response: Response,
    redis_client: Redis = Depends(get_redis),
):
    async with _get_session_factory()() as session:
        async with session.begin():
            svc = AuthService(session, redis_client)
            try:
                user, access_token, refresh_token = await svc.register(
                    company_name=body.company_name,
                    email=body.email,
                    password=body.password,
                )
            except AuthError as exc:
                if "email_already_registered" in str(exc):
                    raise HTTPException(status_code=409, detail="Email already registered")
                raise HTTPException(status_code=400, detail=str(exc))

            await AuditLogRepository(session).log_event(
                event_type="auth.register",
                actor_type="user",
                actor_id=user.id,
                entity_type="user",
                entity_id=user.id,
                company_id=user.company_id,
            )

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    redis_client: Redis = Depends(get_redis),
):
    async with _get_session_factory()() as session:
        async with session.begin():
            svc = AuthService(session, redis_client)
            try:
                user, access_token, refresh_token = await svc.login(
                    email=body.email,
                    password=body.password,
                )
            except AuthError:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            await AuditLogRepository(session).log_event(
                event_type="auth.login",
                actor_type="user",
                actor_id=user.id,
                entity_type="user",
                entity_id=user.id,
                company_id=user.company_id,
            )

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    redis_client: Redis = Depends(get_redis),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    async with _get_session_factory()() as session:
        async with session.begin():
            svc = AuthService(session, redis_client)
            try:
                _, access_token, new_refresh = await svc.refresh(refresh_token)
            except AuthError:
                raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    redis_client: Redis = Depends(get_redis),
):
    if refresh_token:
        async with _get_session_factory()() as session:
            async with session.begin():
                svc = AuthService(session, redis_client)
                await svc.logout(refresh_token)
                await AuditLogRepository(session).log_event(
                    event_type="auth.logout",
                    actor_type="user",
                )

    response.delete_cookie(key=REFRESH_COOKIE, path="/auth")


@router.post("/set-password", response_model=TokenResponse)
async def set_password(
    body: SetPasswordRequest,
    response: Response,
    redis_client: Redis = Depends(get_redis),
):
    """Consume a one-time invite token and set the user's own password."""
    async with _get_session_factory()() as session:
        async with session.begin():
            svc = AuthService(session, redis_client)
            try:
                user = await svc.set_password_via_invite(
                    token=body.token,
                    new_password=body.new_password,
                )
            except AuthError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            access_token = svc._create_access_token(user.id, user.company_id, user.role)
            refresh_token = svc._create_refresh_token()
            await svc._store_refresh_token(refresh_token, user.id)

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: UserResponse = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        company_id=current_user.company_id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )
