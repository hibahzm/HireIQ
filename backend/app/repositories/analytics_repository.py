from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# Evaluation-score histogram bands (inclusive ranges over 0–100).
_SCORE_BANDS = [
    ("0-20", 0, 20),
    ("21-40", 21, 40),
    ("41-60", 41, 60),
    ("61-80", 61, 80),
    ("81-100", 81, 100),
]


class AnalyticsRepository:
    """
    All analytics aggregation SQL lives here (Clean Architecture / Principle III).
    Every query filters by the authenticated company_id explicitly (defense in
    depth, Principle VI / FR-007) — RLS alone is not enough because a privileged
    DB role (e.g. the dev Docker superuser) silently bypasses RLS policies.
    """

    def __init__(self, session: AsyncSession, company_id: str) -> None:
        self._session = session
        self._company_id = str(company_id)

    # ---- per-job (US1) ----------------------------------------------------

    async def job_exists(self, job_id: str) -> bool:
        result = await self._session.execute(
            sa.text("SELECT 1 FROM jobs WHERE id = :job_id AND company_id = :cid"),
            {"job_id": job_id, "cid": self._company_id},
        )
        return result.first() is not None

    async def job_funnel(self, job_id: str) -> dict[str, int]:
        """received / qualified / interviewed / evaluated counts for one job."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT
                    COUNT(*) AS received,
                    COUNT(*) FILTER (WHERE a.screening_status = 'qualified') AS qualified,
                    COUNT(*) FILTER (WHERE i.application_id IS NOT NULL) AS interviewed,
                    COUNT(*) FILTER (WHERE e.application_id IS NOT NULL) AS evaluated
                FROM applications a
                LEFT JOIN interview_sessions i
                    ON i.application_id = a.id AND i.completed_at IS NOT NULL
                LEFT JOIN evaluations e
                    ON e.application_id = a.id
                WHERE a.job_id = :job_id AND a.company_id = :cid
                """
            ),
            {"job_id": job_id, "cid": self._company_id},
        )
        row = result.mappings().one()
        return {k: int(row[k]) for k in ("received", "qualified", "interviewed", "evaluated")}

    async def job_avg_evaluation_score(self, job_id: str) -> float | None:
        result = await self._session.execute(
            sa.text(
                """
                SELECT AVG(e.overall_score) AS avg_score
                FROM evaluations e
                JOIN applications a ON a.id = e.application_id
                WHERE a.job_id = :job_id AND a.company_id = :cid
                """
            ),
            {"job_id": job_id, "cid": self._company_id},
        )
        avg = result.scalar_one_or_none()
        return float(avg) if avg is not None else None

    async def job_score_distribution(self, job_id: str) -> list[dict]:
        case_sql = " ".join(
            f"WHEN e.overall_score BETWEEN {lo} AND {hi} THEN '{band}'"
            for band, lo, hi in _SCORE_BANDS
        )
        result = await self._session.execute(
            sa.text(
                f"""
                SELECT band, COUNT(*) AS count
                FROM (
                    SELECT CASE {case_sql} END AS band
                    FROM evaluations e
                    JOIN applications a ON a.id = e.application_id
                    WHERE a.job_id = :job_id AND a.company_id = :cid
                ) t
                WHERE band IS NOT NULL
                GROUP BY band
                """
            ),
            {"job_id": job_id, "cid": self._company_id},
        )
        counts = {r["band"]: int(r["count"]) for r in result.mappings()}
        # Always return every band (0-filled) in fixed order.
        return [{"band": band, "count": counts.get(band, 0)} for band, _, _ in _SCORE_BANDS]

    async def job_time_to_screen(self, job_id: str) -> dict[str, float] | None:
        """p50/p95 of (screening.completed - screening.started) per application, in seconds."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY dur) AS p50,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY dur) AS p95
                FROM (
                    SELECT EXTRACT(EPOCH FROM (MAX(c.created_at) - MIN(s.created_at))) AS dur
                    FROM applications a
                    JOIN audit_logs s
                        ON s.entity_id = a.id AND s.event_type = 'cv.screening.started'
                    JOIN audit_logs c
                        ON c.entity_id = a.id AND c.event_type = 'cv.screening.completed'
                    WHERE a.job_id = :job_id AND a.company_id = :cid
                    GROUP BY a.id
                ) t
                """
            ),
            {"job_id": job_id, "cid": self._company_id},
        )
        return self._percentiles(result)

    async def job_time_to_evaluate(self, job_id: str) -> dict[str, float] | None:
        """p50/p95 of (evaluations.created_at - interview_sessions.completed_at), in seconds."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY dur) AS p50,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY dur) AS p95
                FROM (
                    SELECT EXTRACT(EPOCH FROM (e.created_at - i.completed_at)) AS dur
                    FROM applications a
                    JOIN interview_sessions i
                        ON i.application_id = a.id AND i.completed_at IS NOT NULL
                    JOIN evaluations e
                        ON e.application_id = a.id
                    WHERE a.job_id = :job_id AND a.company_id = :cid
                ) t
                """
            ),
            {"job_id": job_id, "cid": self._company_id},
        )
        return self._percentiles(result)

    # ---- company-wide (US2) ----------------------------------------------

    async def company_period_counts(self) -> dict[str, int]:
        """Applications created in the current calendar month, total and qualified."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE screening_status = 'qualified') AS qualified
                FROM applications
                WHERE company_id = :cid
                  AND created_at >= date_trunc('month', now())
                """
            ),
            {"cid": self._company_id},
        )
        row = result.mappings().one()
        return {"total": int(row["total"]), "qualified": int(row["qualified"])}

    async def company_period_avg_score(self) -> float | None:
        result = await self._session.execute(
            sa.text(
                """
                SELECT AVG(e.overall_score) AS avg_score
                FROM evaluations e
                JOIN applications a ON a.id = e.application_id
                WHERE a.company_id = :cid
                  AND a.created_at >= date_trunc('month', now())
                """
            ),
            {"cid": self._company_id},
        )
        avg = result.scalar_one_or_none()
        return float(avg) if avg is not None else None

    async def company_jobs(self) -> list[dict]:
        result = await self._session.execute(
            sa.text(
                "SELECT id, title, status FROM jobs "
                "WHERE company_id = :cid ORDER BY created_at DESC"
            ),
            {"cid": self._company_id},
        )
        return [
            {"id": str(r["id"]), "title": r["title"], "status": r["status"]}
            for r in result.mappings()
        ]

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _percentiles(result) -> dict[str, float] | None:
        row = result.mappings().one()
        if row["p50"] is None:
            return None
        return {"p50": float(row["p50"]), "p95": float(row["p95"])}
