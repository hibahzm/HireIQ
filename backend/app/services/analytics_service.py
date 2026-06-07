from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import (
    CompanyOverviewResponse,
    FunnelCounts,
    JobAnalyticsResponse,
    JobSummary,
    ScoreBucket,
    TimingPercentiles,
)


class JobNotFoundError(Exception):
    pass


class AnalyticsService:
    """
    Orchestrates analytics aggregation and applies ÷0-safe rate math.
    All DB access goes through AnalyticsRepository on the RLS-scoped session.
    """

    def __init__(self, repo: AnalyticsRepository) -> None:
        self._repo = repo

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float | None:
        if denominator == 0:
            return None
        return round(numerator / denominator, 4)

    @staticmethod
    def _timing(raw: dict[str, float] | None) -> TimingPercentiles | None:
        return TimingPercentiles(**raw) if raw else None

    async def get_job_analytics(self, job_id: str) -> JobAnalyticsResponse:
        if not await self._repo.job_exists(job_id):
            # Not in the caller's company (RLS) or does not exist.
            raise JobNotFoundError(job_id)

        funnel = await self._repo.job_funnel(job_id)
        avg_score = await self._repo.job_avg_evaluation_score(job_id)
        distribution = await self._repo.job_score_distribution(job_id)
        t_screen = await self._repo.job_time_to_screen(job_id)
        t_eval = await self._repo.job_time_to_evaluate(job_id)

        return JobAnalyticsResponse(
            job_id=job_id,
            funnel=FunnelCounts(**funnel),
            qualification_rate=self._ratio(funnel["qualified"], funnel["received"]),
            interview_completion_rate=self._ratio(funnel["interviewed"], funnel["qualified"]),
            avg_evaluation_score=round(avg_score, 2) if avg_score is not None else None,
            time_to_screen_seconds=self._timing(t_screen),
            time_to_evaluate_seconds=self._timing(t_eval),
            score_distribution=[ScoreBucket(**b) for b in distribution],
        )

    async def get_company_overview(self) -> CompanyOverviewResponse:
        counts = await self._repo.company_period_counts()
        avg_score = await self._repo.company_period_avg_score()
        jobs = await self._repo.company_jobs()

        return CompanyOverviewResponse(
            period=datetime.now(timezone.utc).strftime("%Y-%m"),
            total_applications=counts["total"],
            screening_pass_rate=self._ratio(counts["qualified"], counts["total"]),
            avg_evaluation_score=round(avg_score, 2) if avg_score is not None else None,
            jobs=[JobSummary(**j) for j in jobs],
        )
