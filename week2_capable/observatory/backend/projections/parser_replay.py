"""Replay durable wire frames through the canonical gateway parser."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Literal

from mud_gateway.observe import (
    PARSER_VERSION,
    Coverage,
    WireReference,
    parse,
)

from ..contracts import ParserCounterfactual

Mode = Literal["raw", "minimal", "full"]


def replay_parser(database: Path, mode: Mode) -> ParserCounterfactual:
    """Compare committed parser metrics with the current parser projection."""

    if not database.is_file():
        return _empty(mode)
    connection = sqlite3.connect(
        f"file:{database.resolve()}?mode=ro&immutable=1",
        uri=True,
    )
    try:
        recorded = connection.execute(
            "SELECT payload FROM events WHERE kind = 'parse_metric' "
            "ORDER BY seq"
        ).fetchall()
        blobs = dict(connection.execute("SELECT digest, body FROM blobs"))
    finally:
        connection.close()

    recorded_lines = 0
    recorded_typed = 0
    recorded_version = "unknown"
    frames: list[tuple[int, bytes]] = []
    for (encoded,) in recorded:
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            continue
        recorded_lines += int(payload.get("lines") or 0)
        recorded_typed += int(payload.get("typed") or 0)
        recorded_version = str(payload.get("parser_version") or recorded_version)
        reference = dict(payload.get("wire_ref") or {})
        digest = str(reference.get("digest") or "")
        body = blobs.get(digest)
        if body is not None:
            frames.append(
                (int(reference.get("first_seq") or 0), bytes(body))
            )

    coverage = Coverage()
    for sequence, body in frames:
        reference = WireReference.from_bytes(
            database.name,
            int(sequence),
            int(sequence),
            bytes(body),
        )
        coverage.add(parse(bytes(body), reference))
    recorded_miss = (
        (recorded_lines - recorded_typed) / recorded_lines
        if recorded_lines
        else 0
    )
    return ParserCounterfactual(
        mode=mode,
        frames=len(frames),
        recorded_version=recorded_version,
        replayed_version=PARSER_VERSION,
        recorded_lines=recorded_lines,
        recorded_typed=recorded_typed,
        replayed_lines=coverage.lines,
        replayed_typed=coverage.typed,
        recorded_miss_rate=recorded_miss,
        replayed_miss_rate=coverage.miss_rate,
        typed_delta=coverage.typed - recorded_typed,
    )


def _empty(mode: Mode) -> ParserCounterfactual:
    return ParserCounterfactual(
        mode=mode,
        frames=0,
        recorded_version="unavailable",
        replayed_version=PARSER_VERSION,
        recorded_lines=0,
        recorded_typed=0,
        replayed_lines=0,
        replayed_typed=0,
        recorded_miss_rate=0,
        replayed_miss_rate=0,
        typed_delta=0,
    )
