"""Bounded incremental reads from one append-only agent log."""

from __future__ import annotations

import json
from typing import Any

from ..errors import MalformedSourceError, SourceUnavailableError
from ..models import AgentPage, SessionRecord


class AgentRepository:
    """Read complete JSONL records while preserving an incomplete tail."""

    def __init__(self, session: SessionRecord) -> None:
        self.session = session
        self.source = session.session_dir / "agent.jsonl"

    def page(
        self,
        *,
        offset: int = 0,
        start_line: int = 1,
        limit: int = 250,
    ) -> AgentPage:
        """Read complete records from a byte cursor without losing valid data."""
        if offset < 0:
            raise ValueError("agent offset cannot be negative")
        if start_line < 1:
            raise ValueError("agent line number must be positive")
        if not 1 <= limit <= 1_000:
            raise ValueError("agent limit must be between 1 and 1,000")
        if not self.source.is_file():
            if offset != 0 or start_line != 1:
                raise SourceUnavailableError(self.source)
            return AgentPage(
                records=(),
                next_offset=0,
                next_line=1,
                incomplete_tail=False,
            )
        records: list[dict[str, Any]] = []
        incomplete_tail = False
        line_number = start_line
        with self.source.open("rb") as handle:
            handle.seek(offset)
            while len(records) < limit:
                line_start = handle.tell()
                line = handle.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    handle.seek(line_start)
                    incomplete_tail = True
                    break
                try:
                    value = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise MalformedSourceError(
                        self.source,
                        f"invalid JSONL record at byte {line_start}",
                    ) from error
                if not isinstance(value, dict):
                    raise MalformedSourceError(
                        self.source,
                        f"record at byte {line_start} is not an object",
                    )
                if value.get("session_id") != self.session.session_id:
                    raise MalformedSourceError(
                        self.source,
                        f"record at byte {line_start} has a session mismatch",
                    )
                if value.get("player_id") not in {
                    None,
                    self.session.player_id,
                }:
                    raise MalformedSourceError(
                        self.source,
                        f"record at byte {line_start} has a player mismatch",
                    )
                records.append({"line": line_number, **value})
                line_number += 1
            next_offset = handle.tell()
        return AgentPage(
            records=tuple(records),
            next_offset=next_offset,
            next_line=line_number,
            incomplete_tail=incomplete_tail,
        )
