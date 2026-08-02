"""Small denylist for secret-shaped text in investigation questions."""

from __future__ import annotations

import re

SECRET_PATTERNS = (
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]+\b"),
    re.compile(r"(?i)\b(api[_ -]?key|password|token|authorization)\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
)


def redact_question(value: str) -> str:
    """Remove secret-shaped values before optional external translation."""

    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted
