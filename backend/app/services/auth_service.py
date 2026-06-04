from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.repositories.company_repository import CompanyRepository
from app.repositories.user_repository import UserRepository


class AuthError(Exception):
    pass


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis
        self._settings = get_settings()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def _verify_password(self, password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())

    def _create_access_token(self, user_id: str, company_id: str, role: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "company_id": company_id,
            "role": role,
            "iat": now,
            "exp": now + timedelta(minutes=self._settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        return jwt.encode(payload, self._settings.JWT_SECRET, algorithm=self._settings.JWT_ALGORITHM)

    def _create_refresh_token(self) -> str:
        return str(uuid.uuid4())

    def _refresh_token_key(self, token_hash: str) -> str:
        return f"refresh_token:{token_hash}"

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    # ── public API ────────────────────────────────────────────────────────────

    async def register(
        self, *, company_name: str, email: str, password: str
    ) -> tuple[User, str, str]:
        """Create company + admin user. Returns (user, access_token, refresh_token)."""
        user_repo = UserRepository(self._session)

        existing = await user_repo.get_by_email_global(email)
        if existing:
            raise AuthError("email_already_registered")

        company_repo = CompanyRepository(self._session)
        company = await company_repo.create(company_name)

        password_hash = self._hash_password(password)
        user = await user_repo.create(
            company_id=company.id,
            email=email,
            password_hash=password_hash,
            role="admin",
        )

        access_token = self._create_access_token(user.id, company.id, user.role)
        refresh_token = self._create_refresh_token()

        await self._store_refresh_token(refresh_token, user.id)
        return user, access_token, refresh_token

    async def login(self, *, email: str, password: str) -> tuple[User, str, str]:
        user_repo = UserRepository(self._session)
        user = await user_repo.get_by_email_global(email)
        if not user or not self._verify_password(password, user.password_hash):
            raise AuthError("invalid_credentials")
        if not user.is_active:
            raise AuthError("account_inactive")

        access_token = self._create_access_token(user.id, user.company_id, user.role)
        refresh_token = self._create_refresh_token()
        await self._store_refresh_token(refresh_token, user.id)
        return user, access_token, refresh_token

    async def refresh(self, refresh_token: str) -> tuple[User, str, str]:
        token_hash = self._hash_token(refresh_token)
        key = self._refresh_token_key(token_hash)
        user_id = await self._redis.get(key)
        if not user_id:
            raise AuthError("invalid_refresh_token")

        # Rotate: delete old token
        await self._redis.delete(key)

        user_repo = UserRepository(self._session)
        user = await user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthError("user_not_found")

        new_access_token = self._create_access_token(user.id, user.company_id, user.role)
        new_refresh_token = self._create_refresh_token()
        await self._store_refresh_token(new_refresh_token, user.id)
        return user, new_access_token, new_refresh_token

    async def logout(self, refresh_token: str) -> None:
        token_hash = self._hash_token(refresh_token)
        await self._redis.delete(self._refresh_token_key(token_hash))

    def decode_access_token(self, token: str) -> dict:
        try:
            return jwt.decode(
                token,
                self._settings.JWT_SECRET,
                algorithms=[self._settings.JWT_ALGORITHM],
            )
        except JWTError as exc:
            raise AuthError("invalid_access_token") from exc

    # ── private ───────────────────────────────────────────────────────────────

    async def _store_refresh_token(self, refresh_token: str, user_id: str) -> None:
        token_hash = self._hash_token(refresh_token)
        expire_seconds = self._settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        await self._redis.set(self._refresh_token_key(token_hash), user_id, ex=expire_seconds)
