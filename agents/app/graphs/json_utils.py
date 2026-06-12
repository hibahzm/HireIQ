from __future__ import annotations

import json
from typing import Any


def parse_json_object(content: Any) -> dict[str, Any] | None:
    """
    Extract a JSON object from an LLM response. Tolerates markdown code fences
    and surrounding prose — gpt-4o-mini frequently wraps JSON in ```json blocks,
    and a bare json.loads() on that silently fails, which downstream turns into
    empty dimension scores / bogus rejections.
    """
    text = str(content).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    for candidate in (text, text[text.find("{") : text.rfind("}") + 1]):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
