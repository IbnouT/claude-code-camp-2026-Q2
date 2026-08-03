"""Bounded gateway event reads for one validated session."""

from __future__ import annotations

import json
import sqlite3

from ..database import open_readonly_database, validate_database_schema
from ..errors import MalformedSourceError
from ..models import GatewayEventRecord, SessionRecord

GATEWAY_SCHEMA_VERSION = 1
REQUIRED_GATEWAY_COLUMNS = {
    "events": frozenset(
        {
            "seq",
            "session",
            "at",
            "monotonic",
            "kind",
            "trace_id",
            "payload",
        }
    ),
    "blobs": frozenset({"digest", "body"}),
}


class EventRepository:
    """Read one gateway journal without widening session scope."""

    def __init__(self, session: SessionRecord) -> None:
        self.session = session
        self.source = session.session_dir / "gateway.db"
        validate_database_schema(
            self.source,
            expected_version=GATEWAY_SCHEMA_VERSION,
            required_columns=REQUIRED_GATEWAY_COLUMNS,
        )

    def page(
        self,
        *,
        after: int = 0,
        through: int | None = None,
        limit: int = 500,
    ) -> tuple[GatewayEventRecord, ...]:
        """Read a bounded ordered event page after one retained cursor."""
        if after < 0:
            raise ValueError("event cursor cannot be negative")
        if through is not None and through < after:
            raise ValueError("event range ends before its cursor")
        if not 1 <= limit <= 2_000:
            raise ValueError("event limit must be between 1 and 2,000")
        sql = """
            SELECT seq, session, at, monotonic, kind, trace_id, payload
            FROM events
            WHERE session = ? AND seq > ?
        """
        arguments: list[object] = [
            self.session.gateway_session_id,
            after,
        ]
        if through is not None:
            sql += " AND seq <= ?"
            arguments.append(through)
        sql += " ORDER BY seq LIMIT ?"
        arguments.append(limit)
        try:
            with open_readonly_database(self.source) as database:
                rows = database.execute(sql, arguments).fetchall()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.source,
                "gateway events cannot be read",
            ) from error
        return tuple(self._record(row) for row in rows)

    def latest_sequence(self) -> int:
        """Read the selected gateway session's indexed retained high water."""
        try:
            with open_readonly_database(self.source) as database:
                row = database.execute(
                    """
                    SELECT COALESCE(MAX(seq), 0)
                    FROM events
                    WHERE session = ?
                    """,
                    (self.session.gateway_session_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise MalformedSourceError(
                self.source,
                "gateway high water cannot be read",
            ) from error
        return 0 if row is None else int(row[0])

    def _record(self, row: sqlite3.Row) -> GatewayEventRecord:
        try:
            payload = json.loads(str(row["payload"]))
        except (json.JSONDecodeError, TypeError) as error:
            raise MalformedSourceError(
                self.source,
                f"event {row['seq']} has invalid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise MalformedSourceError(
                self.source,
                f"event {row['seq']} payload is not an object",
            )
        session_id = str(row["session"])
        if session_id != self.session.gateway_session_id:
            raise MalformedSourceError(
                self.source,
                f"event {row['seq']} belongs to another gateway session",
            )
        return GatewayEventRecord(
            sequence=int(row["seq"]),
            session_id=session_id,
            at=float(row["at"]),
            monotonic=float(row["monotonic"]),
            kind=str(row["kind"]),
            trace_id=(None if row["trace_id"] is None else str(row["trace_id"])),
            payload=payload,
        )
