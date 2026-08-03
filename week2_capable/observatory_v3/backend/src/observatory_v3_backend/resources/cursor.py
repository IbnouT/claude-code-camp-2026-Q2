"""Integrity-checked continuation cursors for bounded resources."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from hashlib import sha256

CURSOR_VERSION = 1


class InvalidCursorError(ValueError):
    """A continuation cursor is malformed or belongs to another resource."""


@dataclass(frozen=True, slots=True)
class CursorCoordinates:
    """Stable native keyset coordinates hidden behind the public token."""

    resource: str
    primary: str
    secondary: str


def encode_cursor(coordinates: CursorCoordinates) -> str:
    """Encode one deterministic keyset coordinate with integrity protection."""
    body = json.dumps(
        {
            "p": coordinates.primary,
            "r": coordinates.resource,
            "s": coordinates.secondary,
            "v": CURSOR_VERSION,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = sha256(b"observatory-resource-cursor-v1\0" + body).digest()[:12]
    token = base64.urlsafe_b64encode(body + digest).decode().rstrip("=")
    return f"orc1_{token}"


def decode_cursor(token: str, *, resource: str) -> CursorCoordinates:
    """Validate and decode one cursor for exactly one resource identity."""
    if not token.startswith("orc1_"):
        raise InvalidCursorError("cursor prefix is invalid")
    encoded = token[5:]
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError) as error:
        raise InvalidCursorError("cursor encoding is invalid") from error
    if len(raw) <= 12:
        raise InvalidCursorError("cursor payload is truncated")
    body, supplied = raw[:-12], raw[-12:]
    expected = sha256(b"observatory-resource-cursor-v1\0" + body).digest()[:12]
    if supplied != expected:
        raise InvalidCursorError("cursor integrity check failed")
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidCursorError("cursor payload is invalid") from error
    if not isinstance(value, dict) or value.get("v") != CURSOR_VERSION:
        raise InvalidCursorError("cursor version is unsupported")
    if value.get("r") != resource:
        raise InvalidCursorError("cursor belongs to another resource")
    primary = value.get("p")
    secondary = value.get("s")
    if not isinstance(primary, str) or not isinstance(secondary, str):
        raise InvalidCursorError("cursor coordinates are invalid")
    return CursorCoordinates(
        resource=resource,
        primary=primary,
        secondary=secondary,
    )
