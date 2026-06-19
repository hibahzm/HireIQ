from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# Global table (no RLS): every query MUST filter by company_id (company side) or
# candidate_id (candidate side) — access control lives here, in the app layer.


class SourcingInvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, job_id: str, candidate_id: str, company_id: str, message: str | None = None
    ) -> str | None:
        """Create a pending invitation. Returns the id, or None if one already exists."""
        invitation_id = str(uuid.uuid4())
        result = await self._session.execute(
            sa.text(
                """
                INSERT INTO sourcing_invitations (id, job_id, candidate_id, company_id, message)
                VALUES (:id, :jid, :cid, :coid, :msg)
                ON CONFLICT (job_id, candidate_id) DO NOTHING
                RETURNING id
                """
            ),
            {
                "id": invitation_id,
                "jid": job_id,
                "cid": candidate_id,
                "coid": company_id,
                "msg": message,
            },
        )
        row = result.first()
        return str(row[0]) if row else None

    async def list_for_candidate(self, candidate_id: str) -> list[dict]:
        result = await self._session.execute(
            sa.text(
                """
                SELECT si.id, si.job_id, si.status, si.message, si.created_at,
                       j.title AS job_title, co.name AS company_name
                FROM sourcing_invitations si
                JOIN jobs j ON j.id = si.job_id
                LEFT JOIN companies co ON co.id = si.company_id
                WHERE si.candidate_id = :cid
                ORDER BY si.created_at DESC
                """
            ),
            {"cid": str(candidate_id)},
        )
        return [dict(r) for r in result.mappings().all()]

    async def get_for_candidate(self, *, invitation_id: str, candidate_id: str) -> dict | None:
        result = await self._session.execute(
            sa.text(
                "SELECT id, job_id, candidate_id, company_id, status "
                "FROM sourcing_invitations WHERE id = :id AND candidate_id = :cid"
            ),
            {"id": str(invitation_id), "cid": str(candidate_id)},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def set_status(self, *, invitation_id: str, status: str) -> None:
        await self._session.execute(
            sa.text(
                "UPDATE sourcing_invitations SET status = :st, responded_at = now(), "
                "updated_at = now() WHERE id = :id"
            ),
            {"st": status, "id": str(invitation_id)},
        )
