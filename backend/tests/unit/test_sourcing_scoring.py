"""Unit tests for experience-aware sourcing scoring (feature 018, Phase 2).

The headline requirement: for a required skill, MORE relevant years must rank a
candidate strictly higher than FEWER years. Pure function — no DB/LLM.
"""

from __future__ import annotations

from app.services.sourcing_service import score_experience, target_years_for_level


def _skills(*pairs: tuple[str, float | None]) -> list[dict]:
    return [
        {"skill": s, "years": y, "years_basis": "stated" if y is not None else "unknown"}
        for s, y in pairs
    ]


def test_more_years_outranks_fewer_for_required_skill():
    three = score_experience(
        _skills(("node.js", 3.0)),
        required_skills=["Node.js"],
        experience_level="senior",
    )
    two = score_experience(
        _skills(("node.js", 2.0)),
        required_skills=["Node.js"],
        experience_level="senior",
    )
    assert three["experience_score"] > two["experience_score"]


def test_alias_matching_counts_as_a_match():
    out = score_experience(
        _skills(("NodeJS", 4.0)),
        required_skills=["node.js"],
        experience_level="mid",
    )
    assert out["missing_skills"] == []
    assert any(m["skill"] == "node.js" for m in out["matched_skills"])


def test_missing_required_skill_is_reported_and_lowers_score():
    have = score_experience(_skills(("python", 3.0)), required_skills=["python", "go"])
    assert "go" in have["missing_skills"]
    full = score_experience(_skills(("python", 5.0), ("go", 5.0)), required_skills=["python", "go"])
    assert full["experience_score"] > have["experience_score"]


def test_unknown_years_beats_missing_but_loses_to_quantified():
    unknown = score_experience(_skills(("react", None)), required_skills=["react"])
    missing = score_experience(_skills(("vue", 5.0)), required_skills=["react"])
    quantified = score_experience(_skills(("react", 5.0)), required_skills=["react"])
    assert (
        missing["experience_score"] < unknown["experience_score"] < quantified["experience_score"]
    )


def test_experience_level_sets_year_target():
    assert target_years_for_level("Senior Engineer") == 5.0
    assert target_years_for_level("junior") == 1.0
    assert target_years_for_level(None) == 3.0


def test_accepts_criteria_object_shape():
    """job_criteria stores skills as objects ({skill, priority}), not strings."""
    out = score_experience(
        _skills(("node.js", 4.0)),
        required_skills=[{"skill": "Node.js", "priority": "required"}],
        optional_skills=[{"skill": "AWS", "priority": "optional"}],
        experience_level="senior",
    )
    assert out["missing_skills"] == []
    assert any(m["skill"] == "node.js" for m in out["matched_skills"])


def test_score_capped_at_one():
    out = score_experience(
        _skills(("python", 20.0)),
        required_skills=["python"],
        optional_skills=["python"],
        experience_level="junior",
    )
    assert out["experience_score"] <= 1.0
