from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from redis.asyncio import Redis

from app.api.deps import get_current_candidate, get_current_user
from app.config import get_settings
from app.db import _get_session_factory
from app.models.candidate import Candidate
from app.redis_client import get_redis
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.candidate_cv_repository import CandidateCvRepository
from app.schemas.auth import (
    CandidateRegisterRequest,
    CandidateResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    SetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthError, AuthService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days
# Root path so the cookie is sent regardless of the route prefix the browser
# sees. The frontend reaches auth through the reverse proxy at /api/auth/...,
# which a path="/auth" cookie would never match (the old bug: refresh always
# 401'd after a page refresh, dropping the session).
COOKIE_PATH = "/"


def _cookie_secure() -> bool:
    # Secure cookies are not stored by browsers over plain HTTP, which breaks
    # local dev (http://localhost). Only require Secure in production (HTTPS).
    return get_settings().ENV == "production"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite="strict",
        max_age=COOKIE_MAX_AGE,
        path=COOKIE_PATH,
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
                # Unified login: the type (company vs candidate) is resolved from
                # the credentials, so the user never has to pick at sign-in.
                kind, principal, access_token, refresh_token = await svc.login_any(
                    email=body.email,
                    password=body.password,
                )
            except AuthError:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            if kind == "candidate":
                await AuditLogRepository(session).log_event(
                    event_type="auth.candidate_login",
                    actor_type="candidate",
                    actor_id=principal.id,
                    entity_type="candidate",
                    entity_id=principal.id,
                )
            else:
                await AuditLogRepository(session).log_event(
                    event_type="auth.login",
                    actor_type="user",
                    actor_id=principal.id,
                    entity_type="user",
                    entity_id=principal.id,
                    company_id=principal.company_id,
                )

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


# ── candidate (job-seeker) auth ─────────────────────────────────────────────


@router.post(
    "/candidate/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse
)
async def candidate_register(
    body: CandidateRegisterRequest,
    response: Response,
    redis_client: Redis = Depends(get_redis),
):
    async with _get_session_factory()() as session:
        async with session.begin():
            svc = AuthService(session, redis_client)
            try:
                candidate, access_token, refresh_token = await svc.register_candidate(
                    email=body.email,
                    full_name=body.full_name,
                    password=body.password,
                )
            except AuthError as exc:
                if "email_already_registered" in str(exc):
                    raise HTTPException(status_code=409, detail="Email already registered")
                raise HTTPException(status_code=400, detail=str(exc))

            await AuditLogRepository(session).log_event(
                event_type="auth.candidate_register",
                actor_type="candidate",
                actor_id=candidate.id,
                entity_type="candidate",
                entity_id=candidate.id,
            )

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/candidate/refresh", response_model=TokenResponse)
async def candidate_refresh(
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
                _, access_token, new_refresh = await svc.refresh_candidate(refresh_token)
            except AuthError:
                raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(access_token=access_token)


@router.get("/candidate/me", response_model=CandidateResponse)
async def candidate_me(candidate: Candidate = Depends(get_current_candidate)):
    async with _get_session_factory()() as session:
        async with session.begin():
            has_cv = await CandidateCvRepository(session).exists(candidate.id)
    return CandidateResponse(
        id=candidate.id,
        email=candidate.email,
        full_name=candidate.full_name,
        is_active=candidate.is_active,
        open_to_work=candidate.open_to_work,
        has_cv=has_cv,
    )


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

    response.delete_cookie(key=REFRESH_COOKIE, path=COOKIE_PATH)


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


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    body: ForgotPasswordRequest,
    redis_client: Redis = Depends(get_redis),
):
    """Email a one-time reset link if the address belongs to an active user.
    Always returns 204 — never reveals whether an account exists."""
    async with _get_session_factory()() as session:
        async with session.begin():
            svc = AuthService(session, redis_client)
            result = await svc.request_password_reset(body.email)
            if result:
                user, token = result
                reset_link = f"{get_settings().FRONTEND_ORIGIN}/reset-password?token={token}"
                await NotificationService(redis_client).send_password_reset_email(
                    user.email, reset_link
                )
                await AuditLogRepository(session).log_event(
                    event_type="auth.password_reset_requested",
                    actor_type="user",
                    actor_id=user.id,
                    entity_type="user",
                    entity_id=user.id,
                    company_id=user.company_id,
                )
    return None


@router.post("/reset-password", response_model=TokenResponse)
async def reset_password(
    body: SetPasswordRequest,
    response: Response,
    redis_client: Redis = Depends(get_redis),
):
    """Consume a one-time reset token, set the new password, and log the user in."""
    async with _get_session_factory()() as session:
        async with session.begin():
            svc = AuthService(session, redis_client)
            try:
                user = await svc.reset_password_via_token(
                    token=body.token,
                    new_password=body.new_password,
                )
            except AuthError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

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
