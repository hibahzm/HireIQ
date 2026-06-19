"""In-app talent sourcing: experience-aware hybrid search over candidate CVs.

Combines three signals into a ranked shortlist for a sourcing-enabled job:
  1. dense recall  — pgvector cosine between a job-query embedding and the
     candidate's single whole-CV embedding,
  2. keyword       — Postgres full-text over the candidate's CV tsv,
  3. experience    — a DETERMINISTIC skill/years match against job_criteria, so
     a candidate with more relevant years of a required skill outranks one with
     fewer (e.g. Node.js 3y > 2y). This is the differentiator pure cosine can't give.

Only `open_to_work` candidates are eligible. Contact details (email) are never
returned here — they are revealed only after the candidate accepts an invitation
(spec FR-018).
"""

from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cv_skill_extractor import normalize_skill_name
from app.services.embedding_service import EmbeddingService

# Map a job's experience level to a target years-of-experience for required skills.
_LEVEL_TARGET_YEARS: dict[str, float] = {
    "intern": 0.5,
    "junior": 1.0,
    "entry": 1.0,
    "mid": 3.0,
    "mid-level": 3.0,
    "intermediate": 3.0,
    "senior": 5.0,
    "lead": 7.0,
    "principal": 8.0,
    "staff": 8.0,
}
_DEFAULT_TARGET_YEARS = 3.0
# Credit for a matched skill whose years are unknown (present but unquantified):
# better than missing, worse than a confirmed sufficient duration.
_UNKNOWN_YEARS_CREDIT = 0.5
_OPTIONAL_WEIGHT = 0.3
# Semantic confidence gate: a candidate must clear this whole-CV cosine similarity
# to the job query to be eligible via dense recall — weak/unrelated CVs are dropped
# instead of padding the shortlist. (text-embedding-3-small job↔CV cosine.)
_MIN_SEMANTIC_SIMILARITY = 0.20


def target_years_for_level(experience_level: str | None) -> float:
    if not experience_level:
        return _DEFAULT_TARGET_YEARS
    key = experience_level.strip().lower()
    for level, years in _LEVEL_TARGET_YEARS.items():
        if level in key:
            return years
    return _DEFAULT_TARGET_YEARS


def skill_name(entry) -> str:
    """Coerce a criteria skill entry to its name.

    job_criteria.required_skills/optional_skills are stored as objects
    (``{"skill": "Node.js", "priority": "required"}``), but a plain string is also
    accepted for robustness.
    """
    if isinstance(entry, dict):
        return str(entry.get("skill") or "")
    return str(entry or "")


def skill_names(entries) -> list[str]:
    """Map a criteria skills list to non-empty skill-name strings."""
    return [name for name in (skill_name(e) for e in (entries or [])) if name]


def score_experience(
    candidate_skills: list[dict],
    *,
    required_skills: list,
    optional_skills: list | None = None,
    experience_level: str | None = None,
) -> dict:
    """Pure, deterministic experience score in [0, 1] for a candidate vs a job.

    A required skill scores `min(candidate_years / target_years, 1)`; unknown years
    get partial credit; missing required skills score 0. Optional skills add a small
    weighted bonus. More years of a required skill ⇒ strictly higher score.

    `required_skills`/`optional_skills` may be criteria objects or plain strings.
    """
    required_names = skill_names(required_skills)
    optional_names = skill_names(optional_skills)
    target = target_years_for_level(experience_level)
    by_skill = {normalize_skill_name(s["skill"]): s for s in candidate_skills if s.get("skill")}

    matched: list[dict] = []
    missing: list[str] = []

    req_score = 0.0
    for raw in required_names:
        canonical = normalize_skill_name(raw)
        cand = by_skill.get(canonical)
        if not cand:
            missing.append(raw)
            continue
        years = cand.get("years")
        if years is None:
            contribution = _UNKNOWN_YEARS_CREDIT
        else:
            contribution = min(float(years) / target, 1.0) if target > 0 else 1.0
        req_score += contribution
        matched.append({"skill": canonical, "years": years, "required": True})

    req_component = req_score / len(required_names) if required_names else 0.0

    opt_hits = 0
    for raw in optional_names:
        canonical = normalize_skill_name(raw)
        if canonical in by_skill:
            opt_hits += 1
            matched.append(
                {"skill": canonical, "years": by_skill[canonical].get("years"), "required": False}
            )
    opt_component = (opt_hits / len(optional_names)) if optional_names else 0.0

    score = req_component + _OPTIONAL_WEIGHT * opt_component
    score = min(score, 1.0)
    return {
        "experience_score": round(score, 4),
        "matched_skills": matched,
        "missing_skills": missing,
    }


def _vec(embedding: list[float]) -> str:
    return "[" + ",".join(str(v) for v in embedding) + "]"


async def search_candidates_for_job(
    session: AsyncSession,
    *,
    job_id: str,
    query_text: str,
    required_skills: list[str],
    optional_skills: list[str] | None = None,
    experience_level: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Return a ranked shortlist of open-to-work candidates for the job.

    `query_text` is the job's searchable text (criteria + description). The caller
    supplies job_criteria fields so this service stays free of company-scoped reads.
    """
    embedding, _usage = await EmbeddingService().embed_text(query_text)
    vec = _vec(embedding)

    # Dense + sparse recall over the GLOBAL candidate_cvs, gated to open_to_work.
    dense_q = sa.text(
        """
        SELECT cc.candidate_id, c.full_name, cc.skills,
               1 - (cc.embedding <=> CAST(:vec AS vector)) AS score
        FROM candidate_cvs cc
        JOIN candidates c ON c.id = cc.candidate_id
        WHERE c.open_to_work = true AND cc.embedding IS NOT NULL
          AND (1 - (cc.embedding <=> CAST(:vec AS vector))) >= :min_sim
        ORDER BY score DESC
        LIMIT 50
        """
    )
    sparse_q = sa.text(
        """
        SELECT cc.candidate_id, c.full_name, cc.skills,
               ts_rank(cc.tsv, plainto_tsquery('english', :q)) AS score
        FROM candidate_cvs cc
        JOIN candidates c ON c.id = cc.candidate_id
        WHERE c.open_to_work = true
          AND cc.tsv @@ plainto_tsquery('english', :q)
        ORDER BY score DESC
        LIMIT 50
        """
    )
    dense_res, sparse_res = await asyncio.gather(
        session.execute(dense_q, {"vec": vec, "min_sim": _MIN_SEMANTIC_SIMILARITY}),
        session.execute(sparse_q, {"q": query_text}),
    )
    dense_rows = list(dense_res.mappings().all())
    sparse_rows = list(sparse_res.mappings().all())

    # Recall set = dense (semantic) ∪ sparse (keyword). The dense cosine similarity
    # (0–1) is the semantic signal; keyword-only candidates get semantic 0 but still
    # surface (their experience fit can carry them).
    rows_by_id: dict[str, dict] = {}
    semantic: dict[str, float] = {}
    for row in dense_rows:
        cid = str(row["candidate_id"])
        rows_by_id[cid] = dict(row)
        semantic[cid] = max(0.0, min(float(row["score"]), 1.0))
    for row in sparse_rows:
        cid = str(row["candidate_id"])
        rows_by_id.setdefault(cid, dict(row))
        semantic.setdefault(cid, 0.0)

    # Which of these candidates already have an application to this job (dedup hint).
    invited_ids: set[str] = set()
    if rows_by_id:
        existing = await session.execute(
            sa.text(
                "SELECT candidate_id FROM applications "
                "WHERE job_id = :jid AND candidate_id = ANY(:ids)"
            ),
            {"jid": job_id, "ids": list(rows_by_id.keys())},
        )
        invited_ids = {str(r[0]) for r in existing.all()}

    results: list[dict] = []
    for cid, row in rows_by_id.items():
        skills = row.get("skills") or []
        exp = score_experience(
            skills,
            required_skills=required_skills,
            optional_skills=optional_skills,
            experience_level=experience_level,
        )
        # Skills/years fit matters most (so 3y > 2y on a required skill), but the
        # whole-CV semantic similarity also counts so ranking isn't only about years.
        final = 0.6 * exp["experience_score"] + 0.4 * semantic.get(cid, 0.0)
        results.append(
            {
                "candidate_id": cid,
                "full_name": row.get("full_name"),
                "match_score": round(final, 4),
                "experience_score": exp["experience_score"],
                "matched_skills": exp["matched_skills"],
                "missing_skills": exp["missing_skills"],
                "already_applied": cid in invited_ids,
                # NOTE: email intentionally omitted — revealed only post-acceptance.
            }
        )

    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results[:limit]
