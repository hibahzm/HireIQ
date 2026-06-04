from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_current_user
from app.db import get_db
from app.redis_client import get_redis
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

REFRESH_COOKIE = "refresh_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds


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
    db=Depends(get_db),
    redis=Depends(get_redis),
):
    async for session in db:
        async for r in redis:
            svc = AuthService(session, r)
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

            _set_refresh_cookie(response, refresh_token)
            return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db=Depends(get_db),
    redis=Depends(get_redis),
):
    async for session in db:
        async for r in redis:
            svc = AuthService(session, r)
            try:
                user, access_token, refresh_token = await svc.login(
                    email=body.email,
                    password=body.password,
                )
            except AuthError:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            _set_refresh_cookie(response, refresh_token)
            return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db=Depends(get_db),
    redis=Depends(get_redis),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")
    async for session in db:
        async for r in redis:
            svc = AuthService(session, r)
            try:
                user, access_token, new_refresh = await svc.refresh(refresh_token)
            except AuthError:
                raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

            _set_refresh_cookie(response, new_refresh)
            return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db=Depends(get_db),
    redis=Depends(get_redis),
):
    if refresh_token:
        async for session in db:
            async for r in redis:
                svc = AuthService(session, r)
                await svc.logout(refresh_token)

    response.delete_cookie(key=REFRESH_COOKIE, path="/auth")


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        company_id=current_user.company_id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )
