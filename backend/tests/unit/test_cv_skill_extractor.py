"""Unit tests for the deterministic skill/years normalizer (feature 018, Phase 2).

These pin down the ranking-critical behaviour against messy real-world phrasings
BEFORE any ranking is built on top of it (constitution VIII + the user's
explicit requirement). No LLM or DB involved — pure functions.
"""

from __future__ import annotations

import pytest

from app.services.cv_skill_extractor import (
    normalize_skill_name,
    normalize_skills,
    parse_years_from_evidence,
)

NOW = 2026


@pytest.mark.parametrize(
    ("evidence", "expected_years", "expected_basis"),
    [
        ("Node.js (3 years)", 3.0, "stated"),
        ("3+ years of React", 3.0, "stated"),
        ("2.5 yrs Python", 2.5, "stated"),
        ("Backend dev 2019-2022", 3.0, "inferred_from_dates"),
        ("Backend dev 2019 – 2022", 3.0, "inferred_from_dates"),
        ("React developer 2019 to 2021", 2.0, "inferred_from_dates"),
        ("Using Go since 2021", 5.0, "inferred_from_dates"),
        ("extensive experience in GraphQL", None, "unknown"),
        ("several years with Kafka", None, "unknown"),
        ("proficient in Rust", None, "unknown"),
        ("", None, "unknown"),
    ],
)
def test_parse_years_from_evidence(evidence, expected_years, expected_basis):
    years, basis = parse_years_from_evidence(evidence, now_year=NOW)
    assert years == expected_years
    assert basis == expected_basis


def test_never_fabricates_years_for_vague_phrasing():
    years, basis = parse_years_from_evidence("strong, expert-level Kubernetes", now_year=NOW)
    assert years is None and basis == "unknown"


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("NodeJS", "node.js"),
        ("node js", "node.js"),
        ("React.js", "react"),
        ("  POSTGRES ", "postgresql"),
        ("golang", "go"),
        ("Django", "django"),
    ],
)
def test_normalize_skill_name(raw, canonical):
    assert normalize_skill_name(raw) == canonical


def test_normalize_skills_dedupes_keeping_strongest():
    raw = [
        {"skill": "Node.js", "evidence": "Node.js since 2024"},  # 2 yrs inferred
        {"skill": "NodeJS", "evidence": "Node.js (5 years)"},  # 5 yrs stated → wins
        {"skill": "GraphQL", "evidence": "extensive GraphQL"},  # unknown
    ]
    out = {s["skill"]: s for s in normalize_skills(raw, now_year=NOW)}
    assert out["node.js"]["years"] == 5.0
    assert out["node.js"]["years_basis"] == "stated"
    assert out["graphql"]["years"] is None


def test_known_years_beats_unknown_regardless_of_order():
    raw = [
        {"skill": "python", "evidence": "expert in Python"},  # unknown
        {"skill": "python", "evidence": "Python 4 years"},  # stated → wins
    ]
    out = normalize_skills(raw, now_year=NOW)
    assert out[0]["skill"] == "python"
    assert out[0]["years"] == 4.0


def test_blank_skill_names_dropped():
    raw = [{"skill": "  ", "evidence": "x"}, {"skill": None, "evidence": "y"}]
    assert normalize_skills(raw, now_year=NOW) == []
