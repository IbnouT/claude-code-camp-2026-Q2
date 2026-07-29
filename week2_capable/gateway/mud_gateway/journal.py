"""The event journal: ordered, durable, and the source of truth for everything derived.

SQLite in WAL mode with one writer. Read models are projections that can be thrown away and
rebuilt, so a bug in a projection is never a lost fact.

WHY A JOURNAL RATHER THAN APPENDING JSON LINES. Three properties a text sink cannot give:

- An ordered per-session sequence that a reader can resume from. A live subscriber that drops
  needs to say "I had up to 412", and a file offset is not that number.
- A commit boundary. An event is published to subscribers only after it is committed, so a
  viewer can never show something a crash would erase.
- Integrity. Rows are typed and constrained, so a malformed event fails at write time rather
  than surfacing as a strange chart weeks later.

JSONL export stays available, because the week 1 viewer reads files and its independence is
worth keeping.

WHY THE SEQUENCE IS ASSIGNED BY THE DATABASE. Two writers, or one writer with a retry, can
otherwise produce duplicate numbers, and a subscriber cursor built on duplicates silently skips
events. The sequence comes from a single monotonic column inside the transaction that writes
the row.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Callable

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    session    TEXT    NOT NULL,
    at         REAL    NOT NULL,
    monotonic  REAL    NOT NULL,
    kind       TEXT    NOT NULL,
    trace_id   TEXT,
    payload    TEXT    NOT NULL,
    CHECK (length(kind) > 0),
    CHECK (json_valid(payload))
);
CREATE INDEX IF NOT EXISTS events_by_session ON events(session, seq);
CREATE INDEX IF NOT EXISTS events_by_kind ON events(session, kind, seq);
CREATE TABLE IF NOT EXISTS blobs (
    digest   TEXT PRIMARY KEY,
    body     BLOB NOT NULL
);
"""


@dataclass(frozen=True)
class Event:
    """One committed fact. ``seq`` is assigned by the journal, never by the caller."""

    seq: int
    session: str
    at: float
    monotonic: float
    kind: str
    payload: dict[str, Any]
    trace_id: str | None = None

    def __str__(self) -> str:
        trace = "" if self.trace_id is None else f" trace={self.trace_id}"
        return f"<Event #{self.seq} {self.session} {self.kind}{trace}>"


class JournalError(Exception):
    pass


class Journal:
    """The single writer. Subscribers are notified only after a commit."""

    def __init__(self, path: str | pathlib.Path) -> None:
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        version = int(self._db.execute("PRAGMA user_version").fetchone()[0])
        if version not in (0, SCHEMA_VERSION):
            self._db.close()
            raise JournalError(
                f"journal schema version {version} is unsupported, "
                f"expected {SCHEMA_VERSION}")
        self._db.executescript(SCHEMA)
        if version == 0:
            self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self._subscribers: list[Callable[[Event], None]] = []

    # -- writing ------------------------------------------------------------

    def append(self, session: str, kind: str, payload: dict[str, Any], *,
               trace_id: str | None = None, at: float | None = None,
               monotonic: float | None = None) -> Event:
        """Commit one event and then publish it.

        The order is deliberate: a subscriber that saw an event which a crash later erased
        would be showing something that never happened.
        """
        if not kind:
            raise JournalError("an event needs a kind")
        stamp = time.time() if at is None else at
        mono = time.monotonic() if monotonic is None else monotonic
        try:
            cursor = self._db.execute(
                "INSERT INTO events (session, at, monotonic, kind, trace_id, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session, stamp, mono, kind, trace_id, json.dumps(payload)))
        except sqlite3.IntegrityError as failure:
            raise JournalError(f"rejected {kind!r}: {failure}") from failure
        event = Event(seq=int(cursor.lastrowid), session=session, at=stamp,
                      monotonic=mono, kind=kind, payload=payload, trace_id=trace_id)
        for subscriber in list(self._subscribers):
            subscriber(event)
        return event

    def put_blob(self, body: bytes) -> str:
        """Store a payload once, addressed by content. Returns the digest."""
        import hashlib
        digest = hashlib.sha256(body).hexdigest()[:32]
        self._db.execute("INSERT OR IGNORE INTO blobs (digest, body) VALUES (?, ?)",
                         (digest, body))
        return digest

    def get_blob(self, digest: str) -> bytes | None:
        row = self._db.execute("SELECT body FROM blobs WHERE digest = ?",
                               (digest,)).fetchone()
        return None if row is None else bytes(row["body"])

    # -- reading ------------------------------------------------------------

    def since(self, session: str, after: int = 0, *, kind: str | None = None,
              limit: int | None = None) -> list[Event]:
        """Committed events after a sequence number. This is the resumable cursor."""
        sql = "SELECT * FROM events WHERE session = ? AND seq > ?"
        args: list[Any] = [session, after]
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY seq"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        return [self._row(row) for row in self._db.execute(sql, args)]

    def last_seq(self, session: str) -> int:
        row = self._db.execute("SELECT MAX(seq) AS seq FROM events WHERE session = ?",
                               (session,)).fetchone()
        return 0 if row["seq"] is None else int(row["seq"])

    def sessions(self) -> list[str]:
        return [row["session"] for row in
                self._db.execute("SELECT DISTINCT session FROM events ORDER BY session")]

    def count(self, session: str | None = None) -> int:
        if session is None:
            return int(self._db.execute("SELECT COUNT(*) AS n FROM events")
                       .fetchone()["n"])
        return int(self._db.execute("SELECT COUNT(*) AS n FROM events WHERE session = ?",
                                    (session,)).fetchone()["n"])

    @staticmethod
    def _row(row: sqlite3.Row) -> Event:
        return Event(seq=int(row["seq"]), session=row["session"], at=float(row["at"]),
                     monotonic=float(row["monotonic"]), kind=row["kind"],
                     payload=json.loads(row["payload"]), trace_id=row["trace_id"])

    # -- subscribers and export --------------------------------------------

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        """Register for committed events. Returns the unsubscribe callable."""
        self._subscribers.append(callback)

        def cancel() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return cancel

    def export_jsonl(self, session: str, path: str | pathlib.Path) -> int:
        """Write a session as newline JSON, for readers that consume files."""
        target = pathlib.Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with target.open("w") as handle:
            for event in self.since(session):
                handle.write(json.dumps({
                    "seq": event.seq, "session": event.session, "at": event.at,
                    "kind": event.kind, "trace_id": event.trace_id,
                    **event.payload}) + "\n")
                written += 1
        return written

    def close(self) -> None:
        self._db.close()

    def __str__(self) -> str:
        return (f"<Journal {self.path.name} events={self.count()} "
                f"sessions={len(self.sessions())} subscribers={len(self._subscribers)}>")
