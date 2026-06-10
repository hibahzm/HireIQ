from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings

logger = structlog.get_logger()


def configure_structlog() -> None:
    settings = get_settings()
    # NOTE: structlog.stdlib.add_logger_name is intentionally omitted — it reads
    # `logger.name`, which the PrintLogger from PrintLoggerFactory does not have,
    # so including it makes every structlog log call raise AttributeError.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.ENV == "production":
        # format_exc_info serializes exc_info into the JSON output; the dev
        # ConsoleRenderer formats exceptions itself, so it's only needed here.
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(10),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        if hasattr(request.state, "company_id") and request.state.company_id:
            structlog.contextvars.bind_contextvars(company_id=str(request.state.company_id))

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
