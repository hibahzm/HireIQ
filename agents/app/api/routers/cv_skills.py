from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.graphs.json_utils import parse_json_object
from app.guardrails import registry
from app.prompts.cv_skills import CV_SKILL_EXTRACTION_SYSTEM
from app.usage import usage_event_from_response

logger = structlog.get_logger()

router = APIRouter(prefix="/agents", tags=["cv-skills"])


class CvExtractSkillsRequest(BaseModel):
    cv_text: str


class SkillEvidence(BaseModel):
    skill: str
    evidence: str = ""


class CvExtractSkillsResponse(BaseModel):
    skills: list[SkillEvidence] = Field(default_factory=list)
    usage_events: list[dict[str, Any]] = Field(default_factory=list)


def _build_llm() -> ChatOpenAI:
    from app.config import get_settings

    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.OPENAI_API_KEY,
        temperature=0.0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


@router.post("/cv-extract-skills", response_model=CvExtractSkillsResponse)
async def cv_extract_skills(body: CvExtractSkillsRequest) -> CvExtractSkillsResponse:
    structlog.contextvars.bind_contextvars(agent_type="cv_skill_extraction")

    # Guardrail the input the same way other CV-handling agents do.
    if not registry.check_input(body.cv_text).passed:
        logger.warning("cv_skill_extraction.guardrail_triggered")
        return CvExtractSkillsResponse(skills=[])

    prompt = CV_SKILL_EXTRACTION_SYSTEM.format(cv_text=body.cv_text)
    response = await _build_llm().ainvoke([SystemMessage(content=prompt)])

    usage = usage_event_from_response(response, company_id=None, agent_type="cv_skill_extraction")
    parsed = parse_json_object(response.content) or {}
    raw_skills = parsed.get("skills", []) if isinstance(parsed, dict) else []

    skills: list[SkillEvidence] = []
    for item in raw_skills:
        if isinstance(item, dict) and item.get("skill"):
            skills.append(
                SkillEvidence(skill=str(item["skill"]), evidence=str(item.get("evidence") or ""))
            )

    return CvExtractSkillsResponse(skills=skills, usage_events=[usage] if usage else [])
