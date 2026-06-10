from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """Liveness probe.

    Intentionally does NOT call OpenAI: a readiness/liveness probe must be cheap
    and stable. Calling the OpenAI API on every probe added latency/cost and made
    the check flap (a transient OpenAI hiccup would 503 the agents service, which
    in turn flapped the API's own /health). We only report that the OpenAI key is
    configured — no network call.
    """
    from app.config import get_settings

    settings = get_settings()
    configured = bool(getattr(settings, "OPENAI_API_KEY", ""))
    result = {
        "status": "ok",
        "openai": "configured" if configured else "not_configured",
    }
    return JSONResponse(content=result, status_code=200)
