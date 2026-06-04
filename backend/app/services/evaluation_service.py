from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class EvaluationService:
    """
    Stub — full implementation in Phase 6 (T073).
    InterviewService calls evaluate_from_session() after session_complete;
    this stub prevents ImportError while Phase 6 is pending.
    """

    def __init__(self, session: AsyncSession, redis=None) -> None:
        self._session = session
        self._redis = redis

    async def evaluate_from_session(self, *, session_id: str, company_id: str) -> None:
        # Phase 6 (T073) — not yet implemented.
        logger.info("evaluation.deferred", session_id=session_id)
