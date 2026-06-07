from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    import httpx
    from app.config import get_settings

    settings = get_settings()
    result: dict = {"status": "ok", "openai": "ok"}
    status_code = 200

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            )
            if resp.status_code not in (200, 401):
                raise ValueError(f"unexpected status {resp.status_code}")
    except Exception as exc:
        result["openai"] = f"unreachable: {exc}"
        result["status"] = "degraded"
        status_code = 503

    return JSONResponse(content=result, status_code=status_code)
