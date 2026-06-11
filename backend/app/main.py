from __future__ import annotations

from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.middleware.logging import CorrelationIdMiddleware, configure_structlog
from app.redis_client import close_redis

# Use stdlib logging here (not structlog) so the catch-all can never fail to log
# — it must always be able to return its 500 response.
logger = logging.getLogger("app.unhandled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_structlog()

    # Start APScheduler for hourly session expiry check
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()

    async def expire_sessions():
        from app.db import _get_session_factory
        import sqlalchemy as sa
        from app.services.interview_service import InterviewService
        from app.redis_client import _redis as redis_client

        async with _get_session_factory()() as session:
            async with session.begin():
                svc = InterviewService(session, redis_client)
                await svc.check_and_expire_sessions()

    scheduler.add_job(expire_sessions, "interval", hours=1, id="expire_sessions")
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="HireIQ API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CorrelationIdMiddleware)

    # Catch-all so an unhandled error returns a JSON 500 *inside* the CORS layer.
    # Without this, an uncaught exception is handled above CORSMiddleware and the
    # 500 ships with no CORS headers, which browsers report as an opaque
    # "network error" rather than the actual server failure.
    @app.middleware("http")
    async def catch_unhandled_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            try:
                logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            except Exception:
                pass  # never let logging prevent us from returning a CORS-safe 500
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    from app.api.routers.health import router as health_router
    from app.api.routers.auth import router as auth_router
    from app.api.routers.jobs import router as jobs_router
    from app.api.routers.users import router as users_router
    from app.api.routers.applications import router as applications_router
    from app.api.routers.interviews import router as interviews_router
    from app.api.routers.evaluations import router as evaluations_router
    from app.api.routers.feedback import router as feedback_router
    from app.api.routers.analytics import router as analytics_router
    from app.api.routers.platform import router as platform_router

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(users_router)
    app.include_router(applications_router)
    app.include_router(interviews_router)
    app.include_router(evaluations_router)
    app.include_router(feedback_router)
    app.include_router(analytics_router)
    app.include_router(platform_router)

    return app


app = create_app()
