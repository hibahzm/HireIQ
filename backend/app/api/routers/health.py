from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import httpx
import sqlalchemy as sa

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    from app.db import _get_engine
    from app.redis_client import _redis
    from app.config import get_settings

    settings = get_settings()
    result: dict = {"status": "ok", "db": "ok", "redis": "ok", "agents": "ok"}
    status_code = 200

    # DB check
    try:
        engine = _get_engine()
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception as exc:
        result["db"] = f"error: {exc}"
        result["status"] = "degraded"
        status_code = 503

    # Redis check
    try:
        if _redis is not None:
            await _redis.ping()
        else:
            result["redis"] = "not_initialized"
    except Exception as exc:
        result["redis"] = f"error: {exc}"
        result["status"] = "degraded"
        status_code = 503

    # Agents service check — informational only. A degraded agents service must
    # NOT fail this container's readiness probe (the API can still serve most
    # traffic), so it marks `status: degraded` but keeps HTTP 200. Only the API's
    # own hard dependencies (DB, Redis) return 503.
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.AGENTS_BASE_URL}/health")
            if resp.status_code != 200:
                raise ValueError(f"status {resp.status_code}")
    except Exception as exc:
        result["agents"] = f"error: {exc}"
        if result["status"] == "ok":
            result["status"] = "degraded"

    return JSONResponse(content=result, status_code=status_code)
