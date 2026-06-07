from __future__ import annotations

from pydantic import BaseModel


class FunnelCounts(BaseModel):
    received: int
    qualified: int
    interviewed: int
    evaluated: int


class TimingPercentiles(BaseModel):
    p50: float
    p95: float


class ScoreBucket(BaseModel):
    band: str
    count: int


class JobAnalyticsResponse(BaseModel):
    job_id: str
    funnel: FunnelCounts
    qualification_rate: float | None
    interview_completion_rate: float | None
    avg_evaluation_score: float | None
    time_to_screen_seconds: TimingPercentiles | None
    time_to_evaluate_seconds: TimingPercentiles | None
    score_distribution: list[ScoreBucket]


class JobSummary(BaseModel):
    id: str
    title: str
    status: str


class CompanyOverviewResponse(BaseModel):
    period: str  # current calendar month, e.g. "2026-06"
    total_applications: int
    screening_pass_rate: float | None
    avg_evaluation_score: float | None
    jobs: list[JobSummary]
