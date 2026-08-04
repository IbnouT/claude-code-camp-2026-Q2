"""Deterministic byte budgets and content identities for public resources."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any


def canonical_bytes(value: object) -> bytes:
    """Serialize one public-safe value deterministically."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_identity(prefix: str, value: object) -> tuple[int, str]:
    """Return a stable positive version and opaque cursor for exact content."""
    digest = sha256(prefix.encode() + b"\0" + canonical_bytes(value)).digest()
    # Bounded to the JavaScript safe-integer range: browsers parse JSON numbers
    # as IEEE 754 doubles, so anything wider silently loses precision.
    version = int.from_bytes(digest[:8], "big") & ((1 << 53) - 1)
    return max(1, version), f"{prefix}_{digest.hex()}"


def bounded_json_object(
    value: dict[str, Any],
    *,
    max_bytes: int,
) -> tuple[dict[str, Any], bool]:
    """Return a deterministic JSON object whose canonical form fits the budget."""
    if len(canonical_bytes(value)) <= max_bytes:
        return value, False
    for string_bytes, list_items in (
        (16_384, 100),
        (4_096, 50),
        (1_024, 20),
        (256, 10),
        (64, 5),
    ):
        candidate = _bounded_value(
            value,
            string_bytes=string_bytes,
            list_items=list_items,
        )
        if isinstance(candidate, dict) and len(canonical_bytes(candidate)) <= max_bytes:
            return candidate, True
    result: dict[str, Any] = {}
    for key in sorted(value):
        candidate = _bounded_value(value[key], string_bytes=32, list_items=2)
        trial = {**result, key: candidate}
        if len(canonical_bytes(trial)) > max_bytes:
            break
        result[key] = candidate
    result["_truncated"] = True
    while len(canonical_bytes(result)) > max_bytes and len(result) > 1:
        removable = next(key for key in reversed(tuple(result)) if key != "_truncated")
        del result[removable]
    return result, True


def bounded_text(value: str, *, max_bytes: int) -> tuple[str, bool]:
    """Return UTF-8 text capped at one explicit public response budget."""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


def _bounded_value(
    value: Any,
    *,
    string_bytes: int,
    list_items: int,
) -> Any:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) <= string_bytes:
            return value
        return encoded[:string_bytes].decode("utf-8", errors="ignore")
    if isinstance(value, list | tuple):
        return [
            _bounded_value(
                item,
                string_bytes=string_bytes,
                list_items=list_items,
            )
            for item in value[:list_items]
        ]
    if isinstance(value, dict):
        return {
            str(key): _bounded_value(
                nested,
                string_bytes=string_bytes,
                list_items=list_items,
            )
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    return value
