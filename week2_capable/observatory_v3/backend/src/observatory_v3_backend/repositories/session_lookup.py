"""Direct indexed launcher session lookup."""

from __future__ import annotations

import sqlite3

from ..database import open_readonly_database as open_readonly_database
from ..errors import MalformedSourceError
from ..models import SessionRecord
from .registry import SESSION_COLUMNS, RegistryDatabase


class SessionLookupRepository:
    """Read one session identity without enumerating unrelated sessions."""

    def __init__(self, registry: RegistryDatabase) -> None:
        self.registry = registry

    def get(self, session_id: str) -> SessionRecord | None:
        """Read one session through the launcher's indexed primary key."""
        columns = ", ".join(SESSION_COLUMNS)
        try:
            with open_readonly_database(self.registry.source) as database:
                row = database.execute(
                    f"""
                    SELECT {columns}
                    FROM sessions
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.registry.source,
                "selected session cannot be read",
            ) from error
        return None if row is None else self.registry.session_record(row)
