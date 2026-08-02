"""Read-only SQLite connection and schema validation helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Collection, Mapping
from pathlib import Path

from .errors import (
    MalformedSourceError,
    SourceUnavailableError,
    UnsupportedSchemaError,
)


def open_readonly_database(source: Path) -> sqlite3.Connection:
    """Open an existing SQLite database without write capability."""
    if not source.is_file():
        raise SourceUnavailableError(source)
    try:
        database = sqlite3.connect(
            f"{source.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=0.25,
        )
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA query_only=ON")
        return database
    except sqlite3.Error as error:
        raise MalformedSourceError(source, "database cannot be opened") from error


def validate_database_schema(
    source: Path,
    *,
    expected_version: int,
    required_columns: Mapping[str, Collection[str]],
) -> None:
    """Validate one source once without mutating or negotiating its schema."""
    try:
        with open_readonly_database(source) as database:
            actual_version = int(database.execute("PRAGMA user_version").fetchone()[0])
            if actual_version != expected_version:
                raise UnsupportedSchemaError(
                    source,
                    actual=actual_version,
                    expected=expected_version,
                )
            for table, expected_columns in required_columns.items():
                table_row = database.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type = 'table' AND name = ?
                    """,
                    (table,),
                ).fetchone()
                if table_row is None:
                    raise MalformedSourceError(
                        source,
                        f"required table {table!r} is absent",
                    )
                actual_columns = {
                    str(row["name"])
                    for row in database.execute(f"PRAGMA table_info({table})")
                }
                missing = sorted(set(expected_columns) - actual_columns)
                if missing:
                    raise MalformedSourceError(
                        source,
                        f"table {table!r} is missing {', '.join(missing)}",
                    )
    except (MalformedSourceError, UnsupportedSchemaError):
        raise
    except sqlite3.Error as error:
        raise MalformedSourceError(
            source,
            "schema cannot be inspected",
        ) from error
