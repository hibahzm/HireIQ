from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.middleware.logging import CorrelationIdMiddleware, configure_structlog
from app.redis_client import close_redis


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

    from app.api.routers.health import router as health_router
    from app.api.routers.auth import router as auth_router
    from app.api.routers.jobs import router as jobs_router
    from app.api.routers.users import router as users_router
    from app.api.routers.applications import router as applications_router
    from app.api.routers.interviews import router as interviews_router

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(users_router)
    app.include_router(applications_router)
    app.include_router(interviews_router)

    return app


app = create_app()
