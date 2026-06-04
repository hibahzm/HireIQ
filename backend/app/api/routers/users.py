from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_admin
from app.db import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.users import CreateUserRequest, UpdateRoleRequest, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    async for session in db:
        repo = UserRepository(session)
        users = await repo.list_by_company(current_user.company_id)
        return [UserResponse(**u.__dict__) for u in users]


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    if body.role not in ("admin", "recruiter"):
        raise HTTPException(status_code=422, detail="Role must be admin or recruiter")

    async for session in db:
        repo = UserRepository(session)
        existing = await repo.get_by_email_global(body.email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        # Create user with a locked placeholder password (must use invite flow to log in)
        import bcrypt
        placeholder_hash = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode()

        user = await repo.create(
            company_id=current_user.company_id,
            email=body.email,
            password_hash=placeholder_hash,
            role=body.role,
        )

        # Generate a 24-hour invite token and send a set-password email
        from app.redis_client import get_redis
        from app.services.auth_service import AuthService
        from app.services.notification_service import NotificationService

        try:
            async for r in get_redis():
                svc = AuthService(session, r)
                invite_token = await svc.create_invite_token(user.id)
            invite_link = f"/set-password?token={invite_token}"
            notif = NotificationService()
            await notif.send_user_invite_email(
                to_email=body.email,
                invite_link=invite_link,
            )
        except Exception:
            pass  # Do not fail user creation if Redis/email fails

        return UserResponse(**user.__dict__)


@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    body: UpdateRoleRequest,
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    if body.role not in ("admin", "recruiter"):
        raise HTTPException(status_code=422, detail="Role must be admin or recruiter")

    async for session in db:
        repo = UserRepository(session)
        user = await repo.set_role(user_id, body.role)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse(**user.__dict__)


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    async for session in db:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        await repo.deactivate(user_id)
