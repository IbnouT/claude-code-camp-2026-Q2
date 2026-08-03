"""Bounded exact chunks for sanitized retained JSON values."""

from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from typing import Any

from .bounds import canonical_bytes
from .contracts import ValueChunkResponse

MAX_CONTENT_CHUNK_BYTES = 65_536


def value_chunk(
    value: object,
    *,
    metadata: dict[str, Any],
    offset: int,
    max_bytes: int,
) -> ValueChunkResponse:
    """Return one exact bounded byte range from canonical public-safe JSON."""
    if offset < 0:
        raise ValueError("content offset cannot be negative")
    if not 1 <= max_bytes <= MAX_CONTENT_CHUNK_BYTES:
        raise ValueError("content max_bytes must be between 1 and 65536")
    content = canonical_bytes(value)
    if offset > len(content):
        raise ValueError("content offset exceeds retained value length")
    end = min(len(content), offset + max_bytes)
    return ValueChunkResponse(
        **metadata,
        content_digest=sha256(content).hexdigest(),
        offset=offset,
        next_offset=end if end < len(content) else None,
        total_bytes=len(content),
        encoding="base64",
        chunk=b64encode(content[offset:end]).decode("ascii"),
    )
