#!/usr/bin/env bash
#
# T083 — Full end-to-end validation harness.
#
# Brings up the full stack, waits for health, runs the integration suite (which
# maps 1:1 to the five user stories + tenant isolation in quickstart.md), and
# verifies the asynchronous SLAs:
#   - SC-002: CV screening results within 2 minutes (95% of submissions)
#   - SC-004: evaluation reports within 5 minutes of interview completion
#
# Requires: Docker + Docker Compose, and a real OPENAI_API_KEY exported in the
# environment (the pipelines call OpenAI). Run from the repo root:
#
#   OPENAI_API_KEY=sk-... bash infra/scripts/e2e-validate.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="docker compose -f ${ROOT}/infra/docker-compose.yml"

echo "==> Starting stack"
${COMPOSE} up -d --build

cleanup() {
  echo "==> Tearing down stack"
  ${COMPOSE} down -v
}
trap cleanup EXIT

echo "==> Waiting for API health"
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/health | grep -q '"status":"ok"'; then
    echo "    API healthy"
    break
  fi
  [ "$i" = "60" ] && { echo "API failed to become healthy"; exit 1; }
  sleep 3
done

echo "==> Waiting for agents health"
for i in $(seq 1 30); do
  curl -sf http://localhost:8001/health >/dev/null 2>&1 && { echo "    agents healthy"; break; }
  [ "$i" = "30" ] && { echo "agents failed to become healthy"; exit 1; }
  sleep 3
done

echo "==> Running integration suite (US1–US5 + tenant isolation)"
# Mirrors quickstart.md §CI Smoke Test — each story maps to an integration test.
${COMPOSE} run --rm api pytest tests/integration/ -v

echo
echo "==> Manual SLA verification checklist (quickstart.md):"
echo "    [ ] SC-002: submit 20 concurrent CVs → all screening results < 2 min"
echo "    [ ] SC-004: each completed interview → evaluation report < 5 min"
echo "    Use the curl flows in specs/001-ai-hiring-platform/quickstart.md and"
echo "    confirm timestamps on GET /applications/{id} and GET /jobs/{id}/evaluations."
echo
echo "==> E2E integration suite passed. Complete the SLA checklist above to sign off T083."
