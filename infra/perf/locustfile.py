"""
T084 — Performance audit harness.

Load profile (resolves TODO(PERFORMANCE_BASELINE) from the constitution and
mirrors plan.md §Performance Goals):
  - 50 concurrent users
  - target ~200 req/s on REST endpoints
  - sustained 5 minutes
  - MVP launch scale: ~20 companies, ~500 applications/job

Acceptance gate: synchronous REST endpoints MUST hold p95 ≤ 300 ms under this
profile (Constitution "Performance" standard). The async pipelines (screening,
evaluation) are SLA-measured separately (SC-002 ≤ 2 min, SC-004 ≤ 5 min) and
are NOT part of this synchronous-latency budget.

Run:
    pip install locust
    locust -f infra/perf/locustfile.py \
        --host http://localhost:8000 \
        --users 50 --spawn-rate 10 --run-time 5m --headless \
        --csv perf_report

Then assert the p95 budget against the generated CSV:
    python infra/perf/check_p95.py perf_report_stats.csv
"""
from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, task

PASSWORD = "L0adT3st!pass"


class RecruiterUser(HttpUser):
    """Simulates a recruiter authenticating and browsing the dashboard —
    the synchronous, latency-sensitive REST surface (Constitution p95 budget).
    Excludes CV upload / interview / evaluation, which are async pipelines
    measured under their own SLAs."""

    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        email = f"loadtest-{uuid.uuid4()}@example.com"
        resp = self.client.post(
            "/auth/register",
            json={"company_name": "LoadCo", "email": email, "password": PASSWORD},
            name="POST /auth/register",
        )
        if resp.status_code == 201:
            self.token = resp.json()["access_token"]
        else:
            self.token = ""
        self.headers = {"Authorization": f"Bearer {self.token}"}
        # Seed one job so the list/detail endpoints return data.
        job = self.client.post(
            "/jobs", json={"title": "Backend Engineer"}, headers=self.headers,
            name="POST /jobs",
        )
        self.job_id = job.json().get("id") if job.status_code == 201 else None

    @task(5)
    def list_jobs(self) -> None:
        self.client.get("/jobs", headers=self.headers, name="GET /jobs")

    @task(3)
    def get_job(self) -> None:
        if self.job_id:
            self.client.get(
                f"/jobs/{self.job_id}", headers=self.headers, name="GET /jobs/{id}"
            )

    @task(2)
    def list_applications(self) -> None:
        if self.job_id:
            self.client.get(
                f"/jobs/{self.job_id}/applications",
                headers=self.headers,
                name="GET /jobs/{id}/applications",
            )

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")
