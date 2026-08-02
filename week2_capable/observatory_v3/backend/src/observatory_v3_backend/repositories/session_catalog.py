"""Bounded launcher session catalog reads."""

from __future__ import annotations

import sqlite3

from ..database import open_readonly_database
from ..errors import MalformedSourceError
from ..models import SessionRecord
from .registry import SESSION_COLUMNS, RegistryDatabase


class SessionCatalogRepository:
    """Read lightweight session pages without hydrating retained evidence."""

    def __init__(self, registry: RegistryDatabase) -> None:
        self.registry = registry

    def page(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[SessionRecord, ...]:
        """Read one bounded catalog page ordered by current relevance."""
        if offset < 0:
            raise ValueError("catalog offset cannot be negative")
        if not 1 <= limit <= 500:
            raise ValueError("catalog limit must be between 1 and 500")
        columns = ", ".join(SESSION_COLUMNS)
        try:
            with open_readonly_database(self.registry.source) as database:
                rows = database.execute(
                    f"""
                    SELECT {columns}
                    FROM sessions
                    ORDER BY
                      CASE state
                        WHEN 'running' THEN 0
                        WHEN 'starting' THEN 1
                        WHEN 'draining' THEN 2
                        WHEN 'quarantined' THEN 3
                        ELSE 4
                      END,
                      created_at DESC,
                      session_id
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.registry.source,
                "session catalog cannot be read",
            ) from error
        return tuple(self.registry.session_record(row) for row in rows)
