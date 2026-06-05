from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authed_session, require_admin
from app.models.user import User
from app.redis_client import get_redis
from app.repositories.user_repository import UserRepository
from app.schemas.users import CreateUserRequest, UpdateRoleRequest, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    users = await UserRepository(session).list_by_company(current_user.company_id)
    return [UserResponse(**u.__dict__) for u in users]


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_authed_session),
    redis_client: Redis = Depends(get_redis),
):
    if body.role not in ("admin", "recruiter"):
        raise HTTPException(status_code=422, detail="Role must be admin or recruiter")

    repo = UserRepository(session)
    if await repo.get_by_email_global(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    import bcrypt
    placeholder_hash = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode()

    user = await repo.create(
        company_id=current_user.company_id,
        email=body.email,
        password_hash=placeholder_hash,
        role=body.role,
    )

    try:
        from app.services.auth_service import AuthService
        from app.services.notification_service import NotificationService

        svc = AuthService(session, redis_client)
        invite_token = await svc.create_invite_token(user.id)
        invite_link = f"/set-password?token={invite_token}"
        await NotificationService(redis_client).send_user_invite_email(
            to_email=body.email,
            invite_link=invite_link,
        )
    except Exception:
        pass  # Do not fail user creation if invite email fails

    return UserResponse(**user.__dict__)


@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    body: UpdateRoleRequest,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    if body.role not in ("admin", "recruiter"):
        raise HTTPException(status_code=422, detail="Role must be admin or recruiter")

    user = await UserRepository(session).set_role(user_id, body.role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user.__dict__)


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    repo = UserRepository(session)
    if not await repo.get_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    await repo.deactivate(user_id)
