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

    def live_player_ids(self) -> frozenset[str]:
        """Return every player id with an active session, across all pages.

        The launcher's ``start_available`` must be authoritative, not limited to
        one catalog page, so this reads the full live set from the registry.
        """
        try:
            with open_readonly_database(self.registry.source) as database:
                rows = database.execute(
                    "SELECT DISTINCT player_id FROM sessions "
                    "WHERE state IN ('starting', 'running', 'draining', 'quarantined')"
                ).fetchall()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.registry.source,
                "live players cannot be read",
            ) from error
        return frozenset(str(row[0]) for row in rows)

    def keyset_page(
        self,
        *,
        after_created_at: str | None = None,
        after_session_id: str | None = None,
        player_id: str | None = None,
        limit: int = 50,
    ) -> tuple[SessionRecord, ...]:
        """Read one stable recent page without OFFSET."""
        if not 1 <= limit <= 51:
            raise ValueError("catalog limit must be between 1 and 51")
        if (after_created_at is None) != (after_session_id is None):
            raise ValueError("catalog cursor coordinates must be complete")
        columns = ", ".join(SESSION_COLUMNS)
        clauses: list[str] = []
        arguments: list[object] = []
        if player_id is not None:
            clauses.append("player_id = ?")
            arguments.append(player_id)
        if after_created_at is not None:
            clauses.append("(created_at, session_id) < (?, ?)")
            arguments.extend((after_created_at, after_session_id))
        where = "" if not clauses else f"WHERE {' AND '.join(clauses)}"
        arguments.append(limit)
        try:
            with open_readonly_database(self.registry.source) as database:
                rows = database.execute(
                    f"""
                    SELECT {columns}
                    FROM sessions
                    {where}
                    ORDER BY created_at DESC, session_id DESC
                    LIMIT ?
                    """,
                    arguments,
                ).fetchall()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.registry.source,
                "session catalog cannot be read",
            ) from error
        return tuple(self.registry.session_record(row) for row in rows)


