from __future__ import annotations

import re

# Patterns ordered from most specific to least specific
_PATTERNS: list[tuple[str, str]] = [
    # Email addresses
    (r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[EMAIL]"),
    # Phone numbers (various formats)
    (
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "[PHONE]",
    ),
    # UK phone
    (r"\b(?:\+44\s?|0)(?:\d\s?){9,10}\b", "[PHONE]"),
    # Social security numbers (US)
    (r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b", "[SSN]"),
    # Credit/debit card numbers (basic)
    (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[CARD]"),
    # Dates of birth (common formats)
    (
        r"\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.]\d{2,4}\b",
        "[DOB]",
    ),
    # Addresses — simple heuristic: number followed by street keyword
    (
        r"\b\d+\s+[A-Z][a-zA-Z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl)\b",
        "[ADDRESS]",
    ),
    # Full names (two or three capitalised words NOT at sentence start — heuristic)
    # Intentionally conservative: only redact when followed by identifiers
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), repl) for pat, repl in _PATTERNS]


class PIIRedactor:
    @staticmethod
    def redact(text: str) -> str:
        for pattern, replacement in _COMPILED:
            text = pattern.sub(replacement, text)
        return text
