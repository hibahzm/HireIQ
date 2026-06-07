# Research: HireIQ — AI-Powered Hiring Platform (MVP)

**Feature**: 001-ai-hiring-platform
**Date**: 2026-06-04

---

## 1. SQLAlchemy 2.0 Async + PostgreSQL RLS

**Decision**: Set `app.current_company_id` via `SET LOCAL` inside each SQLAlchemy async session,
executed by the `get_db()` dependency before yielding the session to the route.

**Pattern**:
```python
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        async with session.begin():
            company_id = getattr(request.state, "company_id", None)
            if company_id:
                await session.execute(
                    text("SET LOCAL app.current_company_id = :cid"),
                    {"cid": str(company_id)},
                )
            yield session
```

**Rationale**: `SET LOCAL` is transaction-scoped, so it resets at transaction end — safe with
connection pooling. The api service never yields a session without first setting the tenant
context. Alembic uses a BYPASSRLS migration user.

**Alternatives considered**:
- `SET SESSION` — unsafe with pooling; leaks tenant context across pooled connections.
- Passing company_id to every repository method — error-prone; RLS is a stronger guarantee.

---

## 2. LangGraph Session State — Stateless Agent Turns

**Decision**: The agents service is fully stateless per HTTP request. `InterviewState` is
passed in full with each `/agents/interview/turn` call and returned with `updated_state`.
The api service persists the session state between turns in Redis.

**Redis key**: `interview_session:{session_id}` — TTL 25 hours (24-hour resume window + 1h buffer).

**Rationale**: Keeps the agents service simple and horizontally scalable. No shared state
between agent service instances. Redis TTL automatically handles session expiry.

**Alternatives considered**:
- LangGraph checkpointing to PostgreSQL — adds DB access to agents service (violates constitution
  Principle VI: agents must not access DB directly).
- Storing full state in the WebSocket connection — not viable across reconnects (resume scenario).

---

## 3. pgvector Index Configuration

**Decision**:
- `cv_chunks`: `ivfflat (embedding vector_cosine_ops) WITH (lists = 100)`
- `job_chunks`: `ivfflat (embedding vector_cosine_ops) WITH (lists = 50)`

**Rationale**: ivfflat `lists` should be approximately `sqrt(N)` for good recall/speed balance.
At MVP scale (~1000 CVs per job), lists=100 gives excellent recall. job_chunks are smaller
(one per job), so lists=50 is sufficient. Rebuild index when collections exceed 10k rows.

**Query pattern — hybrid search**:
1. Dense query (pgvector cosine) and sparse query (tsvector) run in parallel via `asyncio.gather`.
2. Each returns top 20 results.
3. Reciprocal Rank Fusion (k=60) merges the two ranked lists.
4. Top 10 unified results sent to LLM context.

**Alternatives considered**:
- HNSW index — better recall at scale but higher memory usage; ivfflat sufficient for MVP.
- Pure dense search — misses exact keyword matches that tsvector handles well (e.g., skill names).

---

## 4. Redis Usage Patterns

**Decision**: Three Redis use cases in the api service:

| Use Case | Key Pattern | TTL | Purpose |
|---|---|---|---|
| Interview session state | `interview_session:{session_id}` | 25h | Persist LangGraph state between turns |
| CV upload rate limiting | `ratelimit:cv:{ip_hash}` | 1h | Max 5 CV uploads per IP per hour |
| Email deduplication | `email:dedup:{template}:{recipient}:{day}` | 24h | Prevent duplicate emails on the same day |

**Rationale**: All three are ephemeral, TTL-bounded use cases with no durability requirement —
Redis is the correct tool. No persistent data belongs in Redis.

---

## 5. JWT Refresh Token Rotation

**Decision**:
- Access token: HS256, 15 min, returned in JSON response body (stored in memory by the frontend).
- Refresh token: HS256, 7 days, stored in `HttpOnly; Secure; SameSite=Strict` cookie.
- On refresh: validate token, issue new access + new refresh, store new refresh token hash
  in Redis (`refresh_token:{token_hash}` → `user_id`, TTL 7 days), invalidate old one.
- Concurrent refresh attempts: first wins; subsequent calls with the same old token fail
  (token already invalidated), forcing re-login.

**Rationale**: HttpOnly cookie prevents XSS token theft. Redis invalidation prevents refresh
token reuse after rotation.

**Alternatives considered**:
- Storing refresh tokens in PostgreSQL — higher latency, unnecessary persistence for short-lived tokens.
- Storing access tokens in localStorage — XSS risk.

---

## 6. WebSocket Authentication for Candidates

**Decision**: The interview WebSocket endpoint at `/interviews/{token}/connect` validates the
`interview_token` path parameter against `applications.interview_token` on connection.
No JWT is required — candidates have no accounts.

**Validation steps on WS connect**:
1. Look up `applications` where `interview_token = token` (unset RLS for this lookup — token is
   the authenticator itself, not a tenant-scoped lookup).
2. Verify `interview_token_expires_at` is in the future (7-day window).
3. Create or retrieve `interview_sessions` record.
4. Load session state from Redis (if resuming an in-progress session).
5. Accept WebSocket connection; set `company_id` for all subsequent DB operations in that session.

**Alternatives considered**:
- Passing token as a query parameter — URL query params are logged by proxies; path params are safer.
- Short-lived JWT issued at invite time — additional complexity with no security benefit over the
  existing single-use token pattern.

---

## 7. Guardrail Registry Integration Pattern

**Decision**: All LangGraph graph nodes that call the LLM MUST call
`await registry.check_input(...)` before the LLM call and `await registry.check_output(...)`
after. The `PIIRedactor.redact()` runs on every output before the agents service returns the
result to the api service.

**GuardContext** carries: `agent_type`, `session_id`, `company_id`, `turn_index`.

**On guard failure**: Return a `GuardResult(passed=False, reason=...)` to the graph node.
The node returns a safe fallback response and logs `guardrail.blocked` to audit_log via
the api service (agents service has no DB access — it returns the blocked flag; api logs it).

**Alternatives considered**:
- Running guards in the api service before forwarding to agents — would require api service to
  understand agent input/output formats, creating tight coupling.
- LangChain callbacks for guard hooks — harder to test and reason about than explicit calls.

---

## 8. Multi-Stage Dockerfile Pattern

**Decision**: Both Python services use the same multi-stage pattern:

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .

FROM python:3.12-slim
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin
COPY app/ app/
USER app
EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Rationale**: Non-root user (security), single worker (Container Apps scales by replicas not
workers), health check required by Azure Container Apps for readiness probes.

---

## 9. Azure Container Apps Ingress Strategy

**Decision**:
- `api` service: external ingress (public HTTPS endpoint)
- `frontend` service: external ingress (public HTTPS endpoint)
- `agents` service: internal ingress only (not reachable from internet; only api can call it)
- `redis` service: runs as a container in the same environment (internal only)

**Internal service communication**: `http://agents` (Container Apps internal DNS).
`AGENTS_INTERNAL_SECRET` header on all api → agents calls.

**Alternatives considered**:
- Azure Service Bus for async agent calls — overkill for MVP; HTTP is simpler and sufficient.
- Azure Cache for Redis — no free tier; container Redis is zero cost for MVP.

---

## 10. OCR Fallback Strategy

**Decision**:
```
1. Extract with PyMuPDF (synchronous, fast, free)
2. If word_count < 50 OR printable_ratio < 0.90 → fallback to Azure Document Intelligence
3. If file is unreadable (corrupted, encrypted) → raise ValidationError → 422 response
4. Store cv_extraction_method ("pymupdf" | "document_intelligence") on applications record
```

**Quality heuristic**: `printable_ratio = len(printable_chars) / len(text)`. This catches
garbled output from image-based PDFs where PyMuPDF extracts noise characters.

**Azure Document Intelligence**: uses `prebuilt-document` model which returns structured layout
(section headings, tables, paragraphs) — better for complex CV formats than raw OCR.
