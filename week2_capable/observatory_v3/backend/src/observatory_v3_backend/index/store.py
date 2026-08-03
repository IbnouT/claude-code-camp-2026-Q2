"""Atomic owner-controlled access to the disposable SQLite index."""

from __future__ import annotations

import fcntl
import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

from .models import (
    CatalogEntry,
    ExperimentCorrelation,
    HierarchyContext,
    IndexedEntity,
    SearchDocument,
    SearchHit,
    SessionCheckpoint,
    SessionIncrement,
    SessionProjection,
    SourceWatermark,
)
from .schema import INDEX_SCHEMA_VERSION, MIGRATIONS, PROJECTOR_VERSION, SCHEMA

BUSY_TIMEOUT_MS = 2_000
WAL_AUTOCHECKPOINT_PAGES = 1_000
SEARCH_TOKEN = re.compile(r"\w+", re.UNICODE)


class UnsupportedIndexSchemaError(RuntimeError):
    """The disposable index belongs to another schema version."""


class IndexCorruptionError(RuntimeError):
    """The disposable index cannot be read safely."""


class IndexWriterUnavailableError(RuntimeError):
    """Another process already owns the single writer lock."""


class IndexProjectionError(RuntimeError):
    """A complete session replacement violated index invariants."""


class IndexProjectionConflict(RuntimeError):
    """An advancement lost its expected-cursor compare and swap."""


@dataclass(frozen=True, slots=True)
class CatalogCursor:
    """Opaque-to-callers keyset coordinates for an indexed catalog page."""

    updated_at: str
    session_id: str


@dataclass(frozen=True, slots=True)
class CatalogPage:
    """One bounded page and its next native keyset coordinate."""

    entries: tuple[CatalogEntry, ...]
    next_cursor: CatalogCursor | None


class IndexStore:
    """Own one disposable index and its process-wide writer lock."""

    def __init__(self, source: Path, *, discard_existing: bool = False) -> None:
        self.source = source.expanduser().resolve()
        self.lock_path = self.source.with_suffix(self.source.suffix + ".lock")
        self._lock_handle: BinaryIO | None = None
        self._acquire_writer()
        try:
            if discard_existing:
                self._discard_files()
            self._initialize()
        except BaseException:
            self.close()
            raise

    @classmethod
    def for_runtime(cls, runtime_root: Path) -> IndexStore:
        """Open the canonical index below one launcher runtime root."""
        return cls(runtime_root / "observatory" / "index-v1.sqlite3")

    @classmethod
    def recreate(cls, source: Path) -> IndexStore:
        """Explicitly discard an unknown or corrupt index under one lock."""
        return cls(source, discard_existing=True)

    def close(self) -> None:
        """Release the process writer lock."""
        handle = self._lock_handle
        if handle is None:
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        self._lock_handle = None

    def __enter__(self) -> IndexStore:
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def reset(self) -> None:
        """Explicitly discard derived data and recreate the current schema."""
        self._discard_files()
        self._initialize()

    def _discard_files(self) -> None:
        for candidate in (
            self.source,
            self.source.with_name(f"{self.source.name}-wal"),
            self.source.with_name(f"{self.source.name}-shm"),
        ):
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass

    def replace_session(self, projection: SessionProjection) -> int:
        """Atomically replace one complete selected-session generation."""
        with closing(self._connect()) as database:
            try:
                database.execute("BEGIN IMMEDIATE")
                row = database.execute(
                    "SELECT generation FROM sessions WHERE session_id = ?",
                    (projection.session_id,),
                ).fetchone()
                generation = 1 if row is None else int(row["generation"]) + 1
                database.execute(
                    "DELETE FROM sessions WHERE session_id = ?",
                    (projection.session_id,),
                )
                database.execute(
                    """
                    INSERT INTO sessions (
                        session_id, player_id, character, state, created_at,
                        updated_at, ended_at, capture_status, latest_goal_id,
                        latest_goal, goal_count, nudge_count, turn_count,
                        iteration_count, record_count, generation,
                        projector_version, capture_gaps
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        projection.session_id,
                        projection.player_id,
                        projection.character,
                        projection.state,
                        projection.created_at,
                        projection.updated_at,
                        projection.ended_at,
                        projection.capture_status,
                        projection.latest_goal_id,
                        projection.latest_goal,
                        projection.goal_count,
                        projection.nudge_count,
                        projection.turn_count,
                        projection.iteration_count,
                        projection.record_count,
                        generation,
                        PROJECTOR_VERSION,
                        json.dumps(
                            projection.capture_gaps,
                            separators=(",", ":"),
                        ),
                    ),
                )
                watermark = projection.watermark
                database.execute(
                    """
                    INSERT INTO source_watermarks (
                        session_id,
                        registry_updated_at,
                        lifecycle_sequence,
                        gateway_session_id,
                        gateway_source_id,
                        gateway_sequence,
                        agent_source_id,
                        agent_offset,
                        agent_next_line,
                        operator_source_id,
                        operator_revision,
                        operator_message_count,
                        operator_history_digest,
                        operator_state,
                        experiment_revision,
                        knowledge_revision
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        projection.session_id,
                        watermark.registry_updated_at,
                        watermark.lifecycle_sequence,
                        watermark.gateway_session_id,
                        watermark.gateway_source_id,
                        watermark.gateway_sequence,
                        watermark.agent_source_id,
                        watermark.agent_offset,
                        watermark.agent_next_line,
                        watermark.operator_source_id,
                        watermark.operator_revision,
                        watermark.operator_message_count,
                        watermark.operator_history_digest,
                        watermark.operator_state,
                        watermark.experiment_revision,
                        watermark.knowledge_revision,
                    ),
                )
                _insert_entities(
                    database,
                    projection.entities,
                    projection.search_documents,
                )
                if projection.experiment is not None:
                    _insert_experiment(database, projection.experiment)
                database.commit()
            except sqlite3.Error as error:
                database.rollback()
                raise IndexProjectionError(
                    f"session {projection.session_id!r} was not replaced"
                ) from error
        return generation

    def checkpoint(self, session_id: str) -> SessionCheckpoint | None:
        """Read one committed session cursor and summary without source access."""
        with closing(self._read_connection()) as database:
            row = database.execute(
                """
                SELECT
                    s.session_id, s.state, s.updated_at, s.ended_at,
                    s.capture_status, s.latest_goal_id, s.latest_goal,
                    s.goal_count, s.nudge_count, s.turn_count,
                    s.iteration_count, s.record_count, s.generation,
                    s.capture_gaps, w.*
                FROM sessions AS s
                JOIN source_watermarks AS w USING (session_id)
                WHERE s.session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            gaps_value = json.loads(str(row["capture_gaps"]))
        except json.JSONDecodeError as error:
            raise IndexCorruptionError(
                f"session {session_id!r} has invalid capture gaps"
            ) from error
        if not isinstance(gaps_value, list) or not all(
            isinstance(value, str) for value in gaps_value
        ):
            raise IndexCorruptionError(
                f"session {session_id!r} has invalid capture gaps"
            )
        return SessionCheckpoint(
            session_id=str(row["session_id"]),
            state=str(row["state"]),
            updated_at=str(row["updated_at"]),
            ended_at=None if row["ended_at"] is None else str(row["ended_at"]),
            capture_status=str(row["capture_status"]),
            latest_goal_id=(
                None if row["latest_goal_id"] is None else str(row["latest_goal_id"])
            ),
            latest_goal=(
                None if row["latest_goal"] is None else str(row["latest_goal"])
            ),
            goal_count=int(row["goal_count"]),
            nudge_count=int(row["nudge_count"]),
            turn_count=int(row["turn_count"]),
            iteration_count=int(row["iteration_count"]),
            record_count=int(row["record_count"]),
            generation=int(row["generation"]),
            watermark=_watermark(row),
            capture_gaps=tuple(gaps_value),
        )

    def hierarchy_context(self, session_id: str) -> HierarchyContext:
        """Read only the committed ancestry needed for one appended suffix."""
        with closing(self._read_connection()) as database:
            session_row = database.execute(
                """
                SELECT id
                FROM entities
                WHERE session_id = ? AND kind = 'session'
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if session_row is None:
                raise IndexCorruptionError(
                    f"session {session_id!r} has no indexed root"
                )
            initial = database.execute(
                """
                SELECT id, title
                FROM entities
                WHERE session_id = ?
                  AND kind = 'goal'
                  AND source_anchor GLOB 'agent:*:initial'
                ORDER BY ordinal
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            tail = database.execute(
                """
                SELECT goal_id, turn_id, iteration_id, occurred_at
                FROM entities
                WHERE session_id = ?
                  AND kind = 'record'
                  AND source_anchor GLOB 'agent:*'
                ORDER BY ordinal DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return HierarchyContext(
            session_entity_id=str(session_row["id"]),
            initial_goal_id=(None if initial is None else str(initial["id"])),
            initial_goal_title=(None if initial is None else str(initial["title"])),
            scoped_goal_id=(
                None
                if tail is None or tail["goal_id"] is None
                else str(tail["goal_id"])
            ),
            current_turn_id=(
                None
                if tail is None or tail["turn_id"] is None
                else str(tail["turn_id"])
            ),
            current_iteration_id=(
                None
                if tail is None or tail["iteration_id"] is None
                else str(tail["iteration_id"])
            ),
            last_agent_at=(
                None
                if tail is None or not str(tail["occurred_at"])
                else str(tail["occurred_at"])
            ),
        )

    def entity_ids_for_anchors(
        self,
        session_id: str,
        anchors: tuple[str, ...],
    ) -> dict[str, str]:
        """Resolve a bounded requested anchor set without scanning entities."""
        if len(anchors) > 2_000:
            raise ValueError("anchor lookup is limited to 2,000 values")
        if not anchors:
            return {}
        placeholders = ",".join("?" for _ in anchors)
        with closing(self._read_connection()) as database:
            rows = database.execute(
                f"""
                SELECT source_anchor, id
                FROM entities
                WHERE session_id = ?
                  AND source_anchor IN ({placeholders})
                """,
                (session_id, *anchors),
            ).fetchall()
        return {str(row["source_anchor"]): str(row["id"]) for row in rows}

    def append_session(
        self,
        *,
        expected: SourceWatermark,
        increment: SessionIncrement,
    ) -> int:
        """Commit one validated suffix if its expected cursor is still current."""
        with closing(self._connect()) as database:
            try:
                database.execute("BEGIN IMMEDIATE")
                row = database.execute(
                    """
                    SELECT s.generation, w.*
                    FROM sessions AS s
                    JOIN source_watermarks AS w USING (session_id)
                    WHERE s.session_id = ?
                    """,
                    (increment.session_id,),
                ).fetchone()
                if row is None or _watermark(row) != expected:
                    raise IndexProjectionConflict(
                        f"session {increment.session_id!r} cursor changed"
                    )
                generation = int(row["generation"]) + 1
                counts = {
                    "goal": 0,
                    "nudge": 0,
                    "turn": 0,
                    "iteration": 0,
                    "record": 0,
                }
                for entity in increment.entities:
                    if entity.kind in counts:
                        counts[entity.kind] += 1
                database.execute(
                    """
                    UPDATE sessions
                    SET state = ?,
                        updated_at = ?,
                        ended_at = ?,
                        capture_status = ?,
                        latest_goal_id = ?,
                        latest_goal = ?,
                        goal_count = goal_count + ?,
                        nudge_count = nudge_count + ?,
                        turn_count = turn_count + ?,
                        iteration_count = iteration_count + ?,
                        record_count = record_count + ?,
                        generation = ?,
                        capture_gaps = ?
                    WHERE session_id = ?
                    """,
                    (
                        increment.state,
                        increment.updated_at,
                        increment.ended_at,
                        increment.capture_status,
                        increment.latest_goal_id,
                        increment.latest_goal,
                        counts["goal"],
                        counts["nudge"],
                        counts["turn"],
                        counts["iteration"],
                        counts["record"],
                        generation,
                        json.dumps(
                            increment.capture_gaps,
                            separators=(",", ":"),
                        ),
                        increment.session_id,
                    ),
                )
                watermark = increment.watermark
                database.execute(
                    """
                    UPDATE source_watermarks
                    SET registry_updated_at = ?,
                        lifecycle_sequence = ?,
                        gateway_session_id = ?,
                        gateway_source_id = ?,
                        gateway_sequence = ?,
                        agent_source_id = ?,
                        agent_offset = ?,
                        agent_next_line = ?,
                        operator_source_id = ?,
                        operator_revision = ?,
                        operator_message_count = ?,
                        operator_history_digest = ?,
                        operator_state = ?,
                        experiment_revision = ?,
                        knowledge_revision = ?
                    WHERE session_id = ?
                    """,
                    (
                        watermark.registry_updated_at,
                        watermark.lifecycle_sequence,
                        watermark.gateway_session_id,
                        watermark.gateway_source_id,
                        watermark.gateway_sequence,
                        watermark.agent_source_id,
                        watermark.agent_offset,
                        watermark.agent_next_line,
                        watermark.operator_source_id,
                        watermark.operator_revision,
                        watermark.operator_message_count,
                        watermark.operator_history_digest,
                        watermark.operator_state,
                        watermark.experiment_revision,
                        watermark.knowledge_revision,
                        increment.session_id,
                    ),
                )
                _insert_entities(
                    database,
                    increment.entities,
                    increment.search_documents,
                )
                if increment.experiment is not None:
                    existing = database.execute(
                        """
                        SELECT experiment_id, run_id
                        FROM experiment_correlations
                        WHERE session_id = ?
                        """,
                        (increment.session_id,),
                    ).fetchone()
                    if existing is None:
                        _insert_experiment(database, increment.experiment)
                    elif (
                        str(existing["experiment_id"]),
                        str(existing["run_id"]),
                    ) != (
                        increment.experiment.experiment_id,
                        increment.experiment.run_id,
                    ):
                        raise IndexProjectionError(
                            "experiment correlation changed after indexing"
                        )
                database.commit()
            except (IndexProjectionConflict, IndexProjectionError):
                database.rollback()
                raise
            except sqlite3.Error as error:
                database.rollback()
                raise IndexProjectionError(
                    f"session {increment.session_id!r} suffix was not committed"
                ) from error
        return generation

    def record_capture_fault(self, session_id: str, code: str) -> int:
        """Record one safe fault without advancing or deleting prior evidence."""
        with closing(self._connect()) as database:
            try:
                database.execute("BEGIN IMMEDIATE")
                row = database.execute(
                    """
                    SELECT generation, capture_status, capture_gaps
                    FROM sessions
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown indexed session {session_id!r}")
                value = json.loads(str(row["capture_gaps"]))
                gaps = (
                    [item for item in value if isinstance(item, str)]
                    if isinstance(value, list)
                    else []
                )
                if code in gaps and str(row["capture_status"]) == "fault":
                    database.rollback()
                    return int(row["generation"])
                if code not in gaps:
                    gaps.append(code)
                generation = int(row["generation"]) + 1
                database.execute(
                    """
                    UPDATE sessions
                    SET capture_status = 'fault',
                        capture_gaps = ?,
                        generation = ?
                    WHERE session_id = ?
                    """,
                    (
                        json.dumps(gaps, separators=(",", ":")),
                        generation,
                        session_id,
                    ),
                )
                database.commit()
            except KeyError:
                database.rollback()
                raise
            except (json.JSONDecodeError, sqlite3.Error) as error:
                database.rollback()
                raise IndexProjectionError(
                    f"session {session_id!r} capture fault was not recorded"
                ) from error
        return generation

    def catalog_page(
        self,
        *,
        limit: int = 50,
        after: CatalogCursor | None = None,
        player_id: str | None = None,
    ) -> CatalogPage:
        """Read one keyset page without counting or opening retained sources."""
        if not 1 <= limit <= 50:
            raise ValueError("catalog limit must be between 1 and 50")
        clauses: list[str] = []
        arguments: list[object] = []
        if player_id is not None:
            clauses.append("player_id = ?")
            arguments.append(player_id)
        if after is not None:
            clauses.append("(updated_at, session_id) < (?, ?)")
            arguments.extend((after.updated_at, after.session_id))
        where = "" if not clauses else f"WHERE {' AND '.join(clauses)}"
        arguments.append(limit + 1)
        with closing(self._read_connection()) as database:
            rows = database.execute(
                f"""
                SELECT
                    session_id, player_id, character, state, created_at,
                    updated_at, ended_at, capture_status, latest_goal,
                    goal_count, nudge_count, turn_count, iteration_count,
                    generation
                FROM sessions
                {where}
                ORDER BY updated_at DESC, session_id DESC
                LIMIT ?
                """,
                arguments,
            ).fetchall()
        entries = tuple(self._catalog_entry(row) for row in rows[:limit])
        next_cursor = (
            None
            if len(rows) <= limit or not entries
            else CatalogCursor(
                updated_at=entries[-1].updated_at,
                session_id=entries[-1].session_id,
            )
        )
        return CatalogPage(entries=entries, next_cursor=next_cursor)

    def catalog_query_plan(self, *, player_scoped: bool = False) -> tuple[str, ...]:
        """Return SQLite query-plan details for the bounded catalog gate."""
        sql = """
            EXPLAIN QUERY PLAN
            SELECT
                session_id, player_id, character, state, created_at,
                updated_at, ended_at, capture_status, latest_goal,
                goal_count, nudge_count, turn_count, iteration_count,
                generation
            FROM sessions
        """
        arguments: tuple[object, ...]
        if player_scoped:
            sql += """
                WHERE player_id = ?
                  AND (updated_at, session_id) < (?, ?)
            """
            arguments = ("player", "cursor", "session")
        else:
            sql += """
                WHERE (updated_at, session_id) < (?, ?)
            """
            arguments = ("cursor", "session")
        sql += " ORDER BY updated_at DESC, session_id DESC LIMIT ?"
        arguments = (*arguments, 51)
        with closing(self._read_connection()) as database:
            rows = database.execute(sql, arguments).fetchall()
        return tuple(str(row["detail"]) for row in rows)

    def search(
        self,
        query: str,
        *,
        session_id: str | None = None,
        player_id: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> tuple[SearchHit, ...]:
        """Search quoted literal terms with deterministic ranking ties."""
        if not 1 <= limit <= 50:
            raise ValueError("search limit must be between 1 and 50")
        expression = _literal_match(query)
        clauses = ["search_fts MATCH ?"]
        arguments: list[object] = [expression]
        for column, value in (
            ("d.session_id", session_id),
            ("d.player_id", player_id),
            ("d.kind", kind),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                arguments.append(value)
        arguments.append(limit)
        with closing(self._read_connection()) as database:
            rows = database.execute(
                f"""
                SELECT
                    d.entity_id, d.session_id, d.player_id, d.kind,
                    d.title, d.body, d.occurred_at,
                    bm25(search_fts) AS rank
                FROM search_fts
                JOIN search_documents AS d
                  ON d.rowid = search_fts.rowid
                WHERE {" AND ".join(clauses)}
                ORDER BY rank, d.occurred_at, d.entity_id
                LIMIT ?
                """,
                arguments,
            ).fetchall()
        return tuple(
            SearchHit(
                entity_id=str(row["entity_id"]),
                session_id=str(row["session_id"]),
                player_id=str(row["player_id"]),
                kind=str(row["kind"]),
                title=str(row["title"]),
                body=str(row["body"]),
                occurred_at=str(row["occurred_at"]),
                rank=float(row["rank"]),
            )
            for row in rows
        )

    def session_for_experiment(self, experiment_id: str, run_id: str) -> str | None:
        """Resolve one stable experiment sample directly to its session."""
        with closing(self._read_connection()) as database:
            row = database.execute(
                """
                SELECT session_id
                FROM experiment_correlations
                WHERE experiment_id = ? AND run_id = ?
                """,
                (experiment_id, run_id),
            ).fetchone()
        return None if row is None else str(row["session_id"])

    def experiment_for_session(self, session_id: str) -> tuple[str, str] | None:
        """Resolve one canonical session back to its experiment and run."""
        with closing(self._read_connection()) as database:
            row = database.execute(
                """
                SELECT experiment_id, run_id
                FROM experiment_correlations
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return None if row is None else (str(row["experiment_id"]), str(row["run_id"]))

    def canonical_session_rows(self, session_id: str) -> tuple[str, ...]:
        """Return a stable logical dump without SQLite storage details."""
        result: list[str] = []
        with closing(self._read_connection()) as database:
            for table, order in (
                ("sessions", "session_id"),
                ("source_watermarks", "session_id"),
                ("entities", "ordinal, id"),
                ("experiment_correlations", "experiment_id, run_id"),
                ("search_documents", "entity_id"),
            ):
                rows = database.execute(
                    f"SELECT * FROM {table} WHERE session_id = ? ORDER BY {order}",
                    (session_id,),
                ).fetchall()
                for row in rows:
                    result.append(
                        json.dumps(
                            {
                                "table": table,
                                **dict(row),
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
        return tuple(result)

    def _acquire_writer(self) -> None:
        self.source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.source.parent, 0o700)
        handle = self.lock_path.open("a+b")
        os.chmod(self.lock_path, 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.close()
            raise IndexWriterUnavailableError(
                f"index writer is already active for {self.source}"
            ) from error
        self._lock_handle = handle

    def _initialize(self) -> None:
        existed = self.source.exists()
        try:
            with closing(self._connect()) as database:
                version = int(database.execute("PRAGMA user_version").fetchone()[0])
                if version < 0 or version > INDEX_SCHEMA_VERSION:
                    raise UnsupportedIndexSchemaError(
                        f"index schema {version} is unsupported, "
                        f"expected {INDEX_SCHEMA_VERSION}"
                    )
                if existed:
                    result = str(database.execute("PRAGMA quick_check").fetchone()[0])
                    if result != "ok":
                        raise IndexCorruptionError(
                            f"index quick check failed: {result}"
                        )
                if version == 0:
                    database.executescript(SCHEMA)
                    database.execute(f"PRAGMA user_version={INDEX_SCHEMA_VERSION}")
                else:
                    while version < INDEX_SCHEMA_VERSION:
                        migration = MIGRATIONS.get(version)
                        if migration is None:
                            raise UnsupportedIndexSchemaError(
                                f"index schema {version} has no migration"
                            )
                        database.executescript(migration)
                        version += 1
                        database.execute(f"PRAGMA user_version={version}")
                    database.executescript(SCHEMA)
                database.commit()
        except (UnsupportedIndexSchemaError, IndexCorruptionError):
            raise
        except sqlite3.Error as error:
            raise IndexCorruptionError(
                f"index {self.source} cannot be initialized"
            ) from error
        os.chmod(self.source, 0o600)

    def _connect(self) -> sqlite3.Connection:
        try:
            database = sqlite3.connect(
                self.source,
                timeout=BUSY_TIMEOUT_MS / 1_000,
                isolation_level=None,
            )
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA foreign_keys=ON")
            database.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            database.execute("PRAGMA journal_mode=WAL")
            database.execute(f"PRAGMA wal_autocheckpoint={WAL_AUTOCHECKPOINT_PAGES}")
            return database
        except sqlite3.Error as error:
            raise IndexCorruptionError(
                f"index {self.source} cannot be opened"
            ) from error

    def _read_connection(self) -> sqlite3.Connection:
        try:
            database = sqlite3.connect(
                f"{self.source.as_uri()}?mode=ro",
                uri=True,
                timeout=BUSY_TIMEOUT_MS / 1_000,
            )
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA query_only=ON")
            database.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            return database
        except sqlite3.Error as error:
            raise IndexCorruptionError(f"index {self.source} cannot be read") from error

    @staticmethod
    def _catalog_entry(row: sqlite3.Row) -> CatalogEntry:
        return CatalogEntry(
            session_id=str(row["session_id"]),
            player_id=str(row["player_id"]),
            character=str(row["character"]),
            state=str(row["state"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            ended_at=None if row["ended_at"] is None else str(row["ended_at"]),
            capture_status=str(row["capture_status"]),
            latest_goal=(
                None if row["latest_goal"] is None else str(row["latest_goal"])
            ),
            goal_count=int(row["goal_count"]),
            nudge_count=int(row["nudge_count"]),
            turn_count=int(row["turn_count"]),
            iteration_count=int(row["iteration_count"]),
            generation=int(row["generation"]),
        )


def _literal_match(query: str) -> str:
    tokens = SEARCH_TOKEN.findall(query)[:32]
    if not tokens:
        raise ValueError("search query must contain at least one word")
    framed = []
    for token in tokens:
        bounded = token[:128].replace('"', '""')
        framed.append(f'"{bounded}"')
    return " AND ".join(framed)


def _watermark(row: sqlite3.Row) -> SourceWatermark:
    return SourceWatermark(
        registry_updated_at=str(row["registry_updated_at"]),
        lifecycle_sequence=int(row["lifecycle_sequence"]),
        gateway_session_id=str(row["gateway_session_id"]),
        gateway_source_id=str(row["gateway_source_id"]),
        gateway_sequence=int(row["gateway_sequence"]),
        agent_source_id=str(row["agent_source_id"]),
        agent_offset=int(row["agent_offset"]),
        agent_next_line=int(row["agent_next_line"]),
        operator_source_id=str(row["operator_source_id"]),
        operator_revision=str(row["operator_revision"]),
        operator_message_count=int(row["operator_message_count"]),
        operator_history_digest=str(row["operator_history_digest"]),
        operator_state=str(row["operator_state"]),
        experiment_revision=(
            None
            if row["experiment_revision"] is None
            else str(row["experiment_revision"])
        ),
        knowledge_revision=(
            None
            if row["knowledge_revision"] is None
            else str(row["knowledge_revision"])
        ),
    )


def _insert_entities(
    database: sqlite3.Connection,
    entities: tuple[IndexedEntity, ...],
    documents: tuple[SearchDocument, ...],
) -> None:
    database.executemany(
        """
        INSERT INTO entities (
            id, session_id, player_id, kind, source_anchor,
            parent_id, goal_id, turn_id, iteration_id, ordinal,
            occurred_at, title, source_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                entity.id,
                entity.session_id,
                entity.player_id,
                entity.kind,
                entity.source_anchor,
                entity.parent_id,
                entity.goal_id,
                entity.turn_id,
                entity.iteration_id,
                entity.ordinal,
                entity.occurred_at,
                entity.title,
                entity.source_ref,
            )
            for entity in entities
        ),
    )
    database.executemany(
        """
        INSERT INTO search_documents (
            entity_id, session_id, player_id, kind,
            occurred_at, title, body
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                document.entity_id,
                document.session_id,
                document.player_id,
                document.kind,
                document.occurred_at,
                document.title,
                document.body,
            )
            for document in documents
        ),
    )


def _insert_experiment(
    database: sqlite3.Connection,
    link: ExperimentCorrelation,
) -> None:
    database.execute(
        """
        INSERT INTO experiment_correlations (
            id, experiment_id, run_id, session_id
        ) VALUES (?, ?, ?, ?)
        """,
        (
            link.id,
            link.experiment_id,
            link.run_id,
            link.session_id,
        ),
    )
