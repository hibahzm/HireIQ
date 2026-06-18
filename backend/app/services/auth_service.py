from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.candidate import Candidate
from app.models.user import User
from app.repositories.candidate_repository import CandidateRepository
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
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "company_id": company_id,
            "role": role,
            "iat": now,
            "exp": now + timedelta(minutes=self._settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            # Unique per token: two tokens minted in the same second must still
            # differ (refresh rotation guarantees a new token).
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(
            payload, self._settings.JWT_SECRET, algorithm=self._settings.JWT_ALGORITHM
        )

    def _create_candidate_token(self, candidate_id: str) -> str:
        """Candidate access token: NO company_id, marked typ='candidate' so company
        routes reject it and candidate routes reject company tokens."""
        now = datetime.now(UTC)
        payload = {
            "sub": candidate_id,
            "typ": "candidate",
            "iat": now,
            "exp": now + timedelta(minutes=self._settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(
            payload, self._settings.JWT_SECRET, algorithm=self._settings.JWT_ALGORITHM
        )

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

        # The brand-new company is the RLS context for inserting its first user
        # (FORCE RLS on `users` rejects inserts with no context set).
        import sqlalchemy as sa

        await self._session.execute(
            sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
            {"cid": str(company.id)},
        )

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

    async def login_any(
        self, *, email: str, password: str
    ) -> tuple[str, object, str, str]:
        """Unified login: resolve the principal type from the credentials.

        Email is globally unique across company users and candidates (FR-002), so
        an email maps to at most one account of one type — the caller never has to
        say which. Returns (kind, principal, access_token, refresh_token) where
        kind is "company" or "candidate".
        """
        user = await UserRepository(self._session).get_by_email_global(email)
        if user:
            if not self._verify_password(password, user.password_hash):
                raise AuthError("invalid_credentials")
            if not user.is_active:
                raise AuthError("account_inactive")
            access = self._create_access_token(user.id, user.company_id, user.role)
            refresh = self._create_refresh_token()
            await self._store_refresh_token(refresh, user.id)
            return "company", user, access, refresh

        candidate = await CandidateRepository(self._session).get_by_email(email)
        if candidate and candidate.password_hash:
            if not self._verify_password(password, candidate.password_hash):
                raise AuthError("invalid_credentials")
            if not candidate.is_active:
                raise AuthError("account_inactive")
            access = self._create_candidate_token(candidate.id)
            refresh = self._create_refresh_token()
            await self._store_refresh_token(refresh, candidate.id)
            return "candidate", candidate, access, refresh

        raise AuthError("invalid_credentials")

    # ── candidate (job-seeker) auth ─────────────────────────────────────────────

    async def register_candidate(
        self, *, email: str, full_name: str, password: str
    ) -> tuple[Candidate, str, str]:
        """Create (or upgrade) a candidate account. Returns (candidate, access, refresh).

        Email is globally unique across ALL accounts: if it already belongs to a
        company user, registration is rejected; if it belongs to an apply-only
        candidate record (no password), that same row is upgraded to an account so
        the one-email-one-identity invariant holds across the account and the
        public external-apply routes.
        """
        if await UserRepository(self._session).get_by_email_global(email):
            raise AuthError("email_already_registered")

        cand_repo = CandidateRepository(self._session)
        password_hash = self._hash_password(password)
        existing = await cand_repo.get_by_email(email)
        if existing and existing.password_hash:
            raise AuthError("email_already_registered")
        if existing:
            candidate = await cand_repo.set_account_credentials(
                candidate_id=existing.id, full_name=full_name, password_hash=password_hash
            )
        else:
            candidate = await cand_repo.create_account(
                email=email, full_name=full_name, password_hash=password_hash
            )

        access_token = self._create_candidate_token(candidate.id)
        refresh_token = self._create_refresh_token()
        await self._store_refresh_token(refresh_token, candidate.id)
        return candidate, access_token, refresh_token

    async def refresh_candidate(self, refresh_token: str) -> tuple[Candidate, str, str]:
        token_hash = self._hash_token(refresh_token)
        key = self._refresh_token_key(token_hash)
        candidate_id = await self._redis.get(key)
        if not candidate_id:
            raise AuthError("invalid_refresh_token")
        await self._redis.delete(key)

        candidate = await CandidateRepository(self._session).get_by_id(candidate_id)
        # A company user's refresh token resolves to a non-candidate id here and
        # fails safe (not found), so this path only succeeds for real candidates.
        if not candidate or not candidate.password_hash or not candidate.is_active:
            raise AuthError("candidate_not_found")

        new_access_token = self._create_candidate_token(candidate.id)
        new_refresh_token = self._create_refresh_token()
        await self._store_refresh_token(new_refresh_token, candidate.id)
        return candidate, new_access_token, new_refresh_token

    async def refresh(self, refresh_token: str) -> tuple[User, str, str]:
        token_hash = self._hash_token(refresh_token)
        key = self._refresh_token_key(token_hash)
        user_id = await self._redis.get(key)
        if not user_id:
            raise AuthError("invalid_refresh_token")

        # Rotate: delete old token
        await self._redis.delete(key)

        user_repo = UserRepository(self._session)
        user = await user_repo.get_by_id_global(user_id)
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

    def _user_tokens_key(self, user_id: str) -> str:
        return f"user_refresh_tokens:{user_id}"

    async def _store_refresh_token(self, refresh_token: str, user_id: str) -> None:
        token_hash = self._hash_token(refresh_token)
        expire_seconds = self._settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        await self._redis.set(self._refresh_token_key(token_hash), user_id, ex=expire_seconds)
        # Per-user index so every refresh token can be revoked at once (e.g. when an
        # admin deactivates the user, or after a password reset). Refresh is already
        # is_active-gated; this gives an immediate, total cutoff.
        index_key = self._user_tokens_key(user_id)
        await self._redis.sadd(index_key, token_hash)
        await self._redis.expire(index_key, expire_seconds)

    async def revoke_user_refresh_tokens(self, user_id: str) -> None:
        """Delete all stored refresh tokens for a user (deactivation / password reset)."""
        index_key = self._user_tokens_key(user_id)
        hashes = await self._redis.smembers(index_key)
        for token_hash in hashes:
            await self._redis.delete(self._refresh_token_key(token_hash))
        await self._redis.delete(index_key)

    # ── invite / set-password ─────────────────────────────────────────────────

    def _invite_token_key(self, token: str) -> str:
        return f"invite_token:{token}"

    async def create_invite_token(self, user_id: str) -> str:
        """Generate a 24-hour invite token for a newly created user."""
        token = str(uuid.uuid4())
        await self._redis.set(self._invite_token_key(token), user_id, ex=86400)
        return token

    async def set_password_via_invite(self, *, token: str, new_password: str) -> User:
        """Consume an invite token and set the user's password."""
        user_id = await self._redis.get(self._invite_token_key(token))
        if not user_id:
            raise AuthError("invalid_or_expired_invite_token")

        if len(new_password) < 8:
            raise AuthError("password_too_short")

        await self._redis.delete(self._invite_token_key(token))

        from datetime import datetime

        import sqlalchemy as sa

        from app.models.user import User as UserModel

        user_repo = UserRepository(self._session)
        user = await user_repo.get_by_id_global(user_id)
        if not user:
            raise AuthError("user_not_found")

        # Set the RLS context for the UPDATE (no auth context exists yet).
        await self._session.execute(
            sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
            {"cid": str(user.company_id)},
        )

        new_hash = self._hash_password(new_password)
        await self._session.execute(
            sa.update(UserModel)
            .where(UserModel.id == user_id)
            .values(password_hash=new_hash, updated_at=datetime.now(UTC))
        )

        user = await user_repo.get_by_id(user_id)
        if not user:
            raise AuthError("user_not_found")
        return user

    # ── forgot / reset password ─────────────────────────────────────────────────

    def _reset_token_key(self, token: str) -> str:
        return f"reset_token:{token}"

    async def request_password_reset(self, email: str) -> tuple[User, str] | None:
        """Mint a 1-hour reset token for an active user. Returns (user, token), or
        None when there is no active user — the caller must not reveal which."""
        user = await UserRepository(self._session).get_by_email_global(email)
        if not user or not user.is_active:
            return None
        token = str(uuid.uuid4())
        await self._redis.set(self._reset_token_key(token), str(user.id), ex=3600)
        return user, token

    async def reset_password_via_token(self, *, token: str, new_password: str) -> User:
        """Consume a reset token, set the new password, and revoke existing sessions."""
        user_id = await self._redis.get(self._reset_token_key(token))
        if not user_id:
            raise AuthError("invalid_or_expired_reset_token")
        if len(new_password) < 8:
            raise AuthError("password_too_short")
        await self._redis.delete(self._reset_token_key(token))

        import sqlalchemy as sa

        from app.models.user import User as UserModel

        user_repo = UserRepository(self._session)
        user = await user_repo.get_by_id_global(user_id)
        if not user:
            raise AuthError("user_not_found")

        await self._session.execute(
            sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
            {"cid": str(user.company_id)},
        )
        await self._session.execute(
            sa.update(UserModel)
            .where(UserModel.id == user_id)
            .values(password_hash=self._hash_password(new_password), updated_at=datetime.now(UTC))
        )
        # A password reset invalidates any existing sessions.
        await self.revoke_user_refresh_tokens(user_id)

        user = await user_repo.get_by_id(user_id)
        if not user:
            raise AuthError("user_not_found")
        return user
