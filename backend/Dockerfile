# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder
# uv for fast, reproducible installs (pin to a specific release for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/uv uv pip install --system .

FROM python:3.12-slim
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini alembic.ini
COPY entrypoint.sh entrypoint.sh
RUN mkdir -p /app/storage && chown app:app /app/storage && chmod +x entrypoint.sh
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
# Runs `alembic upgrade head` then launches uvicorn, so a deploy can never leave
# the schema behind the code (the cause of the candidate "password_hash" 500).
CMD ["./entrypoint.sh"]
