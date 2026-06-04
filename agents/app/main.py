from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.middleware.logging import CorrelationIdMiddleware, configure_structlog


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_structlog()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="HireIQ Agents", version="0.1.0", lifespan=lifespan)

    # Reject requests that do not carry the shared internal secret
    @app.middleware("http")
    async def require_internal_secret(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        secret = request.headers.get("X-Internal-Secret")
        if secret != settings.AGENTS_INTERNAL_SECRET:
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        return await call_next(request)

    app.add_middleware(CorrelationIdMiddleware)

    from app.api.routers.health import router as health_router
    from app.api.routers.job_setup import router as job_setup_router
    from app.api.routers.screening import router as screening_router
    from app.api.routers.interview import router as interview_router

    app.include_router(health_router)
    app.include_router(job_setup_router)
    app.include_router(screening_router)
    app.include_router(interview_router)

    return app


app = create_app()
