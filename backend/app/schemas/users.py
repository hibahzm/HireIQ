from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateUserRequest(BaseModel):
    email: str
    role: str = "recruiter"


class UpdateRoleRequest(BaseModel):
    role: str


class UserResponse(BaseModel):
    id: str
    company_id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserInviteResponse(UserResponse):
    invite_link: str | None = None
