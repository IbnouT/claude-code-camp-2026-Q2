"""Bounded lifecycle reads from the launcher registry."""

from __future__ import annotations

import json
import sqlite3

from ..database import open_readonly_database
from ..errors import MalformedSourceError
from ..models import LifecycleRecord
from .registry import RegistryDatabase


class LifecycleRepository:
    """Read lifecycle transitions for one session identity."""

    def __init__(self, registry: RegistryDatabase) -> None:
        self.source = registry.source

    def page(
        self,
        session_id: str,
        *,
        after: int = 0,
        limit: int = 250,
    ) -> tuple[LifecycleRecord, ...]:
        """Read ordered lifecycle evidence after one registry cursor."""
        if after < 0:
            raise ValueError("lifecycle cursor cannot be negative")
        if not 1 <= limit <= 1_000:
            raise ValueError("lifecycle limit must be between 1 and 1,000")
        try:
            with open_readonly_database(self.source) as database:
                rows = database.execute(
                    """
                    SELECT id, session_id, at, state, detail
                    FROM lifecycle
                    WHERE session_id = ? AND id > ?
                    ORDER BY id
                    LIMIT ?
                    """,
                    (session_id, after, limit),
                ).fetchall()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.source,
                "lifecycle records cannot be read",
            ) from error
        return tuple(self._record(row) for row in rows)

    def _record(self, row: sqlite3.Row) -> LifecycleRecord:
        try:
            detail = json.loads(str(row["detail"]))
        except json.JSONDecodeError as error:
            raise MalformedSourceError(
                self.source,
                f"lifecycle record {row['id']} has invalid detail",
            ) from error
        if not isinstance(detail, dict):
            raise MalformedSourceError(
                self.source,
                f"lifecycle record {row['id']} detail is not an object",
            )
        return LifecycleRecord(
            sequence=int(row["id"]),
            session_id=str(row["session_id"]),
            at=str(row["at"]),
            state=str(row["state"]),
            detail=detail,
        )
