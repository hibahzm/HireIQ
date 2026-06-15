from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_event(
        self,
        *,
        event_type: str,
        actor_type: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | str | None = None,
        metadata: dict[str, Any] | None = None,
        company_id: uuid.UUID | str | None = None,
        actor_id: uuid.UUID | str | None = None,
    ) -> None:
        await self._session.execute(
            sa.text(
                """
                INSERT INTO audit_logs
                    (company_id, actor_id, actor_type, event_type,
                     entity_type, entity_id, metadata)
                VALUES
                    (CAST(:company_id AS uuid), CAST(:actor_id AS uuid),
                     :actor_type, :event_type, :entity_type,
                     CAST(:entity_id AS uuid), CAST(:metadata AS jsonb))
                """
            ),
            {
                "company_id": str(company_id) if company_id else None,
                "actor_id": str(actor_id) if actor_id else None,
                "actor_type": actor_type,
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "metadata": __import__("json").dumps(metadata or {}),
            },
        )

    async def list_by_company(
        self, company_id: uuid.UUID | str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Most-recent audit events for one company (newest first). Company-scoped
        for the admin activity view; RLS + explicit company_id keep it tenant-safe."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT id, actor_type, actor_id, event_type,
                       entity_type, entity_id, metadata, created_at
                FROM audit_logs
                WHERE company_id = CAST(:company_id AS uuid)
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"company_id": str(company_id), "limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]
