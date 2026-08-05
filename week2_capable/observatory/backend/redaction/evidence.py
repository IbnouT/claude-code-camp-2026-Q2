"""Recursive sanitization for evidence that crosses the read API boundary."""

from __future__ import annotations

import re
from typing import Any

from .text import redact_question

LOCAL_PATH = re.compile(
    r"(?:(?:/Users|/home|/private|/var/folders|/tmp)/[^\s\"']+|"
    r"[A-Za-z]:\\\\Users\\\\[^\s\"']+)"
)
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}


def sanitize_evidence(value: Any, key: str = "") -> Any:
    """Remove credential-shaped values and local paths from retained evidence."""

    if key.casefold() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, str):
        return LOCAL_PATH.sub("[LOCAL_PATH]", redact_question(value))
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_evidence(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_evidence(item) for item in value]
    return value
