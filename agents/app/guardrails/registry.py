from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# Toxic / harmful input keywords (extend as needed)
_TOXIC_PATTERNS = [
    "how to make a bomb",
    "how to kill",
    "self-harm",
    "suicide method",
    "child pornography",
    "csam",
    "synthesize drugs",
    "synthesise drugs",
]

# Prompt-injection markers
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "disregard all prior",
    "you are now",
    "act as chatgpt",
    "act as an unfiltered",
    "act as a different assistant",
    "jailbreak",
    "dan mode",
    "pretend you are",
]


@dataclass
class GuardResult:
    passed: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class GuardRegistry:
    """
    Wraps all LLM calls. check_input / check_output must be called
    before and after every agent LLM invocation.
    """

    def check_input(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        lowered = text.lower()

        for pattern in _TOXIC_PATTERNS:
            if pattern in lowered:
                logger.warning("guardrail.input.blocked", reason="toxic_content", pattern=pattern)
                return GuardResult(passed=False, reason="toxic_content")

        for pattern in _INJECTION_PATTERNS:
            if pattern in lowered:
                logger.warning(
                    "guardrail.input.blocked", reason="prompt_injection", pattern=pattern
                )
                return GuardResult(passed=False, reason="prompt_injection")

        return GuardResult(passed=True)

    def check_output(self, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        lowered = text.lower()

        for pattern in _TOXIC_PATTERNS:
            if pattern in lowered:
                logger.warning("guardrail.output.blocked", reason="toxic_output", pattern=pattern)
                return GuardResult(passed=False, reason="toxic_output")

        return GuardResult(passed=True)


# Module-level singleton
registry = GuardRegistry()
