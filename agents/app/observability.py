"""Optional Langfuse tracing for the agent graphs.

If LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are configured (via Key Vault in prod
or dev Vault locally), every LangGraph/LLM call gets traced. If they're absent — or
the langfuse package isn't installed — this degrades to a no-op so local and prod
both run unchanged. Callers pass the returned list as ``config={"callbacks": ...}``.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

_handler = None
_initialized = False


def get_langfuse_callbacks() -> list:
    """Return [langfuse_handler] when tracing is enabled, else []. Initialised once."""
    global _handler, _initialized
    if not _initialized:
        _initialized = True
        from app.config import get_settings

        settings = get_settings()
        if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
            try:
                from langfuse.callback import CallbackHandler

                _handler = CallbackHandler(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    host=settings.LANGFUSE_HOST,
                )
                logger.info("langfuse.enabled", host=settings.LANGFUSE_HOST)
            except Exception as exc:  # missing package / bad config — never block agents
                logger.warning("langfuse.init_failed", error=str(exc))
                _handler = None
        else:
            logger.info("langfuse.disabled")
    return [_handler] if _handler else []
