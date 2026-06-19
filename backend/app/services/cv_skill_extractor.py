"""Structured skill + years-of-experience extraction from a CV.

Design (per spec 018, Phase 2): the LLM does only the *fuzzy* part — pulling out
`{skill, evidence}` pairs (the skill name plus the snippet that mentions it). The
*ranking-critical* part — turning messy phrasings into a number of years — is a
DETERMINISTIC, fully-tested normalizer here. This keeps the experience-aware
ranking (3y > 2y) reproducible and ensures we never fabricate a year count.

Output schema per skill:
    {"skill": str, "years": float | None,
     "years_basis": "stated" | "inferred_from_dates" | "unknown",
     "evidence": str}
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

# Canonicalize common skill aliases so "NodeJS", "node js", "Node.js" all match.
_SKILL_ALIASES: dict[str, str] = {
    "nodejs": "node.js",
    "node js": "node.js",
    "node": "node.js",
    "node.js": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "postgre": "postgresql",
    "py": "python",
    "golang": "go",
    "k8s": "kubernetes",
    "gcp": "google cloud",
}

# "3 years", "3+ yrs", "3.5 years of experience"
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
# "2019-2022", "2019 – 2022", "2019 to 2022"
_RANGE_RE = re.compile(r"(19|20)(\d{2})\s*(?:-|–|—|to)\s*(19|20)(\d{2})", re.IGNORECASE)
# "since 2021", "from 2021"
_SINCE_RE = re.compile(r"(?:since|from)\s+((?:19|20)\d{2})", re.IGNORECASE)
# Vague phrasing that must NOT be assigned a number.
_VAGUE_RE = re.compile(
    r"\b(extensive|several|various|many|strong|solid|proficient|expert|familiar)\b",
    re.IGNORECASE,
)


def normalize_skill_name(name: str) -> str:
    key = re.sub(r"\s+", " ", name.strip().lower())
    return _SKILL_ALIASES.get(key, key)


def parse_years_from_evidence(
    evidence: str, *, now_year: int | None = None
) -> tuple[float | None, str]:
    """Return (years, years_basis) from a free-text evidence snippet.

    Never invents a number: vague/absent experience yields (None, "unknown").
    """
    now_year = now_year or datetime.now(UTC).year
    text = evidence or ""

    m = _YEARS_RE.search(text)
    if m:
        return float(m.group(1)), "stated"

    m = _RANGE_RE.search(text)
    if m:
        start = int(m.group(1) + m.group(2))
        end = int(m.group(3) + m.group(4))
        if end >= start:
            return float(end - start) or 1.0, "inferred_from_dates"

    m = _SINCE_RE.search(text)
    if m:
        start = int(m.group(1))
        if now_year >= start:
            return float(now_year - start) or 1.0, "inferred_from_dates"

    return None, "unknown"


def normalize_skills(raw_skills: list[dict], *, now_year: int | None = None) -> list[dict]:
    """Normalize raw {skill, evidence} pairs into the structured schema.

    Deduplicates by canonical skill name, keeping the highest confident year count
    (a stated/inferred number beats unknown; a larger number beats a smaller one).
    """
    by_skill: dict[str, dict] = {}
    for raw in raw_skills:
        if not isinstance(raw, dict):
            continue
        name = raw.get("skill")
        if not name or not str(name).strip():
            continue
        canonical = normalize_skill_name(str(name))
        evidence = str(raw.get("evidence") or "").strip()
        years, basis = parse_years_from_evidence(evidence, now_year=now_year)

        existing = by_skill.get(canonical)
        candidate = {
            "skill": canonical,
            "years": years,
            "years_basis": basis,
            "evidence": evidence,
        }
        if existing is None or _is_stronger(candidate, existing):
            by_skill[canonical] = candidate

    return sorted(by_skill.values(), key=lambda s: s["skill"])


def _is_stronger(a: dict, b: dict) -> bool:
    """Prefer a known year count over unknown, then the larger count."""
    a_known = a["years"] is not None
    b_known = b["years"] is not None
    if a_known != b_known:
        return a_known
    if a_known and b_known:
        return a["years"] > b["years"]
    return False


# ── LLM extraction (fuzzy part) — delegated to the agents service ─────────────


async def extract_skills_from_cv(cv_text: str) -> list[dict]:
    """Call the agents service to pull {skill, evidence} pairs, then normalize.

    Returns the structured, normalized skill list. On any failure returns [] so
    the caller (CV upload) never fails just because skill extraction did.
    """
    import httpx
    import structlog

    from app.config import get_settings

    logger = structlog.get_logger()
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.AGENTS_BASE_URL}/agents/cv-extract-skills",
                json={"cv_text": cv_text},
                headers={"X-Internal-Secret": settings.AGENTS_INTERNAL_SECRET},
            )
            resp.raise_for_status()
            raw = resp.json().get("skills", [])
    except Exception as exc:  # noqa: BLE001 — extraction is best-effort
        logger.warning("cv_skill_extraction.failed", error=str(exc))
        return []
    return normalize_skills(raw)


async def run_skill_extraction_background(*, candidate_id: str, cv_text: str) -> None:
    """Fire-and-forget: extract structured skills and persist to candidate_cvs.

    Owns its own DB session (runs as an asyncio.Task). candidate_cvs is global
    (no RLS), so no tenant context is required. Best-effort: failures are logged,
    never raised, so a CV upload is never blocked by skill extraction.
    """
    import structlog

    from app.db import _get_session_factory
    from app.repositories.candidate_cv_repository import CandidateCvRepository

    logger = structlog.get_logger()
    try:
        skills = await extract_skills_from_cv(cv_text)
        if not skills:
            return
        async with _get_session_factory()() as session:
            async with session.begin():
                await CandidateCvRepository(session).update_skills(
                    candidate_id=candidate_id, skills=skills
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cv_skill_extraction.persist_failed", error=str(exc))
