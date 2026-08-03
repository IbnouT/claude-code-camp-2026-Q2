"""SQLite persistence for lifecycle commands."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import Command, CommandState, CommandSubmission

SCHEMA_VERSION = 1


class CommandStore:
    """Own command identity, idempotency, and terminal results."""

    def __init__(self, runtime_root: Path) -> None:
        root = runtime_root.expanduser().resolve() / "observatory"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "commands-v1.sqlite3"
        self._lock = threading.RLock()
        self._database = sqlite3.connect(
            self.path,
            timeout=0.1,
            check_same_thread=False,
        )
        self.path.chmod(0o600)
        self._database.row_factory = sqlite3.Row
        self._database.execute("PRAGMA busy_timeout = 100")
        self._database.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._database.close()

    def submit(self, value: CommandSubmission) -> tuple[Command, bool]:
        """Persist before effects and return an existing idempotent command."""
        with self._lock:
            row = self._database.execute(
                "SELECT * FROM commands WHERE idempotency_key = ?",
                (value.idempotency_key,),
            ).fetchone()
            if row is not None:
                existing = _command(row)
                if _identity(existing) != _submission_identity(value):
                    raise ValueError("idempotency key was used for another command")
                return existing, False
            command_id = uuid4().hex
            submitted_at = _now()
            self._database.execute(
                """
                INSERT INTO commands (
                    id, idempotency_key, action, actor, player_id, session_id,
                    expected_cursor, instruction, force, state, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    command_id,
                    value.idempotency_key,
                    value.action,
                    value.actor,
                    value.player_id,
                    value.session_id,
                    value.expected_cursor,
                    value.instruction,
                    int(value.force),
                    submitted_at,
                ),
            )
            self._database.commit()
            return self.get(command_id), True

    def existing(self, value: CommandSubmission) -> Command | None:
        """Return one identical idempotent command before current-state checks."""
        with self._lock:
            row = self._database.execute(
                "SELECT * FROM commands WHERE idempotency_key = ?",
                (value.idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        command = _command(row)
        if _identity(command) != _submission_identity(value):
            raise ValueError("idempotency key was used for another command")
        return command

    def get(self, command_id: str) -> Command:
        with self._lock:
            row = self._database.execute(
                "SELECT * FROM commands WHERE id = ?",
                (command_id,),
            ).fetchone()
        if row is None:
            raise KeyError(command_id)
        return _command(row)

    def recoverable(self) -> tuple[Command, ...]:
        with self._lock:
            rows = self._database.execute(
                """
                SELECT * FROM commands
                WHERE state IN ('queued', 'running')
                ORDER BY submitted_at, id
                """
            ).fetchall()
        return tuple(_command(row) for row in rows)

    def transition(
        self,
        command_id: str,
        state: CommandState,
        *,
        result_code: str | None = None,
        result_detail: str | None = None,
        result_session_id: str | None = None,
    ) -> Command:
        now = _now()
        with self._lock:
            current = self.get(command_id)
            started_at = current.started_at
            finished_at = current.finished_at
            if state == "running" and started_at is None:
                started_at = now
            if state in {"succeeded", "failed"}:
                finished_at = now
            self._database.execute(
                """
                UPDATE commands
                SET state = ?, started_at = ?, finished_at = ?,
                    result_code = ?, result_detail = ?, result_session_id = ?
                WHERE id = ?
                """,
                (
                    state,
                    started_at,
                    finished_at,
                    result_code,
                    result_detail,
                    result_session_id,
                    command_id,
                ),
            )
            self._database.commit()
            return self.get(command_id)

    def _migrate(self) -> None:
        with self._lock:
            self._database.executescript(
                """
                CREATE TABLE IF NOT EXISTS command_schema (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    session_id TEXT,
                    expected_cursor TEXT,
                    instruction TEXT,
                    force INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result_code TEXT,
                    result_detail TEXT,
                    result_session_id TEXT
                );
                """
            )
            row = self._database.execute(
                "SELECT version FROM command_schema"
            ).fetchone()
            if row is None:
                self._database.execute(
                    "INSERT INTO command_schema (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif int(row[0]) != SCHEMA_VERSION:
                raise RuntimeError("unsupported lifecycle command schema")
            self._database.commit()


def _command(row: sqlite3.Row) -> Command:
    return Command(
        id=str(row["id"]),
        idempotency_key=str(row["idempotency_key"]),
        action=str(row["action"]),  # type: ignore[arg-type]
        actor=str(row["actor"]),
        player_id=str(row["player_id"]),
        session_id=None if row["session_id"] is None else str(row["session_id"]),
        expected_cursor=(
            None if row["expected_cursor"] is None else str(row["expected_cursor"])
        ),
        instruction=None if row["instruction"] is None else str(row["instruction"]),
        force=bool(row["force"]),
        state=str(row["state"]),  # type: ignore[arg-type]
        submitted_at=str(row["submitted_at"]),
        started_at=None if row["started_at"] is None else str(row["started_at"]),
        finished_at=None if row["finished_at"] is None else str(row["finished_at"]),
        result_code=None if row["result_code"] is None else str(row["result_code"]),
        result_detail=(
            None if row["result_detail"] is None else str(row["result_detail"])
        ),
        result_session_id=(
            None if row["result_session_id"] is None else str(row["result_session_id"])
        ),
    )


def _identity(command: Command) -> tuple[object, ...]:
    return (
        command.action,
        command.actor,
        command.player_id,
        command.session_id,
        command.expected_cursor,
        command.instruction,
        command.force,
    )


def _submission_identity(value: CommandSubmission) -> tuple[object, ...]:
    return (
        value.action,
        value.actor,
        value.player_id,
        value.session_id,
        value.expected_cursor,
        value.instruction,
        value.force,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
