"""Read registered player sessions and their journals without taking ownership."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from mud_gateway.journal import Event
from mud_gateway.reset_client import (
    request_knowledge_restore,
    request_reset,
)


class RuntimeSourceError(RuntimeError):
    """The local runtime registry or one selected journal cannot be read."""


#: Lifecycle states in which a row claims its session is still running.
CLAIMED_STATES = frozenset({"starting", "running", "draining", "quarantined"})


def _process_alive(pid: int | None) -> bool:
    """True when a process with that id exists and we may signal it."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It exists and belongs to somebody else, which still counts.
        return True
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class RuntimeSession:
    """One launcher-owned session safe for public Observatory discovery."""

    id: str
    player_id: str
    character: str
    gateway_session_id: str
    state: str
    control_state: str | None
    control_available: bool
    capture_status: str
    created_at: str
    updated_at: str
    ended_at: str | None
    stop_mode: str | None
    event_count: int
    latest_seq: int
    legacy: bool
    #: The process the launcher recorded. A row can outlive its process,
    #: so this is what tells a stale claim from a running one.
    pid: int | None
    objective: str | None
    goal_count: int
    nudge_count: int

    @property
    def live(self) -> bool:
        """Running, and the process saying so is still there.

        A run killed outright never writes its ending, so its row keeps
        claiming to be running for as long as the file survives. Trusting
        the row alone shows a session as live for days after the process
        that owned it has gone.
        """
        return self.state in CLAIMED_STATES and _process_alive(self.pid)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "player_id": self.player_id,
            "character": self.character,
            "gateway_session_id": self.gateway_session_id,
            "state": self.state,
            "control_state": self.control_state,
            "control_available": self.control_available,
            "capture_status": self.capture_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "stop_mode": self.stop_mode,
            "event_count": self.event_count,
            "latest_seq": self.latest_seq,
            "legacy": self.legacy,
            "live": self.live,
            "objective": self.objective,
            "goal_count": self.goal_count,
            "nudge_count": self.nudge_count,
        }


@dataclass(frozen=True)
class RuntimeSessionActivity:
    """What one session has produced, measured without parsing any of it."""

    latest_seq: int
    agent_log_size: int
    live: bool

    def __str__(self) -> str:
        return (
            f"<RuntimeSessionActivity latest_seq={self.latest_seq} "
            f"agent_log_size={self.agent_log_size} live={self.live}>"
        )


class RuntimeSource:
    """Discover all players and sessions from the launcher registry."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir.expanduser().resolve()
        self.registry = self.config_dir / "registry.db"

    @property
    def available(self) -> bool:
        return self.registry.is_file() or bool(self._measured_roots())

    def _measured_roots(self) -> tuple[Path, ...]:
        """Roots of measured runs, which keep their own state on purpose.

        A benchmark run writes into a tree of its own so it cannot disturb
        the player it is measuring. That isolation is about writing, not
        about looking: a run nobody can watch is a run nobody can check.
        """
        found = [
            registry.parent
            for registry in sorted(
                self.config_dir.glob("benchmarks/*/attempts/*/registry.db")
            )
        ]
        return tuple(found)

    def _roots(self) -> tuple[Path, ...]:
        roots = [self.config_dir] if self.registry.is_file() else []
        roots.extend(self._measured_roots())
        return tuple(roots)

    def sessions(self) -> tuple[RuntimeSession, ...]:
        found: list[RuntimeSession] = []
        for root in self._roots():
            found.extend(self._sessions_of(root))
        return tuple(found)

    def _sessions_of(self, root: Path) -> tuple[RuntimeSession, ...]:
        registry = root / "registry.db"
        if not registry.is_file():
            return ()
        try:
            with self._database(registry) as database:
                rows = database.execute(
                    self._session_query(
                        database,
                        """
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
                        """,
                    )
                ).fetchall()
        except sqlite3.Error as error:
            raise RuntimeSourceError("runtime registry is unreadable") from error
        return tuple(self._session(row, root) for row in rows)

    def session(self, session_id: str) -> RuntimeSession | None:
        """Read one registered session by its key instead of by sweeping."""
        for root in self._roots():
            registry = root / "registry.db"
            if not registry.is_file():
                continue
            try:
                with self._database(registry) as database:
                    row = database.execute(
                        self._session_query(database, "WHERE session_id = ?"),
                        (session_id,),
                    ).fetchone()
            except sqlite3.Error as error:
                raise RuntimeSourceError(
                    "runtime registry is unreadable"
                ) from error
            if row is not None:
                return self._session(row, root)
        return None

    def activity(self, session_id: str) -> RuntimeSessionActivity | None:
        """Report what a session has produced without reading any of it.

        The agent log is measured and never opened, so a log growing
        through a model call is seen for the price of one stat.
        """
        located = self._locate(session_id)
        if located is None:
            return None
        row, directory = located
        _count, latest = self._journal_summary(directory / "gateway.db")
        try:
            size = (directory / "agent.jsonl").stat().st_size
        except OSError:
            size = 0
        pid = None if row["pid"] is None else int(row["pid"])
        return RuntimeSessionActivity(
            latest_seq=latest,
            agent_log_size=size,
            live=str(row["state"]) in CLAIMED_STATES and _process_alive(pid),
        )

    def events(
        self,
        session_id: str,
        *,
        after: int = 0,
        through: int | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        session_dir = self._session_dir(session_id)
        journal = session_dir / "gateway.db"
        if not journal.is_file() or journal.stat().st_size == 0:
            return []
        sql = (
            "SELECT seq, session, at, monotonic, kind, payload, trace_id "
            "FROM events WHERE seq > ?"
        )
        arguments: list[Any] = [after]
        if through is not None:
            sql += " AND seq <= ?"
            arguments.append(through)
        sql += " ORDER BY seq"
        if limit is not None:
            sql += " LIMIT ?"
            arguments.append(limit)
        try:
            with self._database(journal) as database:
                table = database.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'events'"
                ).fetchone()
                if table is None:
                    return []
                rows = database.execute(sql, arguments).fetchall()
        except sqlite3.Error as error:
            raise RuntimeSourceError(
                f"session {session_id!r} journal is unreadable"
            ) from error
        events: list[Event] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload"]))
            except (json.JSONDecodeError, TypeError) as error:
                raise RuntimeSourceError(
                    f"session {session_id!r} contains invalid event payload"
                ) from error
            if not isinstance(payload, dict):
                raise RuntimeSourceError(
                    f"session {session_id!r} contains a non-object event payload"
                )
            events.append(
                Event(
                    seq=int(row["seq"]),
                    session=str(row["session"]),
                    at=float(row["at"]),
                    monotonic=float(row["monotonic"]),
                    kind=str(row["kind"]),
                    payload=payload,
                    trace_id=(
                        None
                        if row["trace_id"] is None
                        else str(row["trace_id"])
                    ),
                )
            )
        return events

    def wire_blob(self, session_id: str, sequence: int) -> tuple[Event, bytes] | None:
        """Read one exact retained wire body without widening session scope."""
        event = next(
            iter(
                self.events(
                    session_id,
                    after=max(0, sequence - 1),
                    through=sequence,
                    limit=1,
                )
            ),
            None,
        )
        if event is None or event.seq != sequence or event.kind != "wire":
            return None
        digest = event.payload.get("digest")
        if not isinstance(digest, str) or len(digest) != 32:
            raise RuntimeSourceError(
                f"session {session_id!r} wire event {sequence} has no valid digest"
            )
        journal = self._session_dir(session_id) / "gateway.db"
        try:
            with self._database(journal) as database:
                row = database.execute(
                    "SELECT body FROM blobs WHERE digest = ?",
                    (digest,),
                ).fetchone()
        except sqlite3.Error as error:
            raise RuntimeSourceError(
                f"session {session_id!r} wire evidence is unreadable"
            ) from error
        if row is None:
            raise RuntimeSourceError(
                f"session {session_id!r} wire event {sequence} is missing its blob"
            )
        body = bytes(row["body"])
        actual = hashlib.sha256(body).hexdigest()[:32]
        if actual != digest:
            raise RuntimeSourceError(
                f"session {session_id!r} wire event {sequence} failed integrity"
            )
        return event, body

    def agent_events(self, session: RuntimeSession) -> list[dict[str, Any]]:
        """Read every complete agent record the selected session has written.

        A live run is written to while it is read, so its tail can be half
        a line, or half a character of one. Both end after the last
        newline, so a live log is read up to there and the rest belongs to
        the next read. An ended log gains nothing more, so its last line is
        a whole record with or without a closing newline.
        """
        source = self._session_dir(session.id) / "agent.jsonl"
        if not source.is_file():
            return []
        records: list[dict[str, Any]] = []
        try:
            raw = source.read_bytes()
        except OSError as error:
            raise RuntimeSourceError(
                f"session {session.id!r} agent log is unreadable"
            ) from error
        end = raw.rfind(b"\n") + 1 if session.live else len(raw)
        try:
            text = raw[:end].decode("utf-8")
        except UnicodeDecodeError as error:
            raise RuntimeSourceError(
                f"session {session.id!r} agent log is not valid text"
            ) from error
        # Line numbers are record ids that cross to agent_record, which
        # seeks by them, so both must split lines the same way: on \n
        # alone, the JSONL separator.
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        for index, line in enumerate(lines, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeSourceError(
                    f"session {session.id!r} agent log line {index} is invalid"
                ) from error
            records.append(self._agent_record(session, value, index))
        return records

    def agent_record(
        self,
        session: RuntimeSession,
        line: int,
    ) -> dict[str, Any] | None:
        """Read one agent record by seeking its line in the log.

        The file is streamed and only the matching line is parsed, so one
        record costs the same whatever the log has grown to.
        """
        if line < 1:
            return None
        source = self._session_dir(session.id) / "agent.jsonl"
        if not source.is_file():
            return None
        try:
            with source.open("rb") as handle:
                # Binary iteration ends lines on \n alone, the JSONL
                # separator, numbering them exactly as agent_events numbers
                # them: the same line is the same record id on both sides.
                for index, raw in enumerate(handle, start=1):
                    if index < line:
                        continue
                    if index > line or not raw.endswith(b"\n"):
                        return None
                    try:
                        value = json.loads(raw.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError) as error:
                        raise RuntimeSourceError(
                            f"session {session.id!r} agent log line {line} "
                            "is invalid"
                        ) from error
                    return self._agent_record(session, value, line)
        except OSError as error:
            raise RuntimeSourceError(
                f"session {session.id!r} agent log is unreadable"
            ) from error
        return None

    @staticmethod
    def _agent_record(
        session: RuntimeSession,
        value: Any,
        line: int,
    ) -> dict[str, Any]:
        """Accept one parsed agent line only under the session it claims."""
        if not isinstance(value, dict):
            raise RuntimeSourceError(
                f"session {session.id!r} agent log line {line} is not an object"
            )
        if value.get("session_id") != session.id:
            raise RuntimeSourceError(
                f"session {session.id!r} agent log identity mismatch"
            )
        if value.get("player_id") not in {None, session.player_id}:
            raise RuntimeSourceError(
                f"session {session.id!r} agent log player mismatch"
            )
        return {"line": line, **value}

    def operator_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Read the agent-owned durable operator message history."""
        source = self._session_dir(session_id) / "operator-messages.json"
        if not source.is_file():
            return []
        value = self._object(source)
        messages = value.get("messages")
        if value.get("version") != 1 or not isinstance(messages, list):
            raise RuntimeSourceError(
                f"session {session_id!r} operator message history is invalid"
            )
        records: list[dict[str, Any]] = []
        for message in messages:
            if not isinstance(message, dict):
                raise RuntimeSourceError(
                    f"session {session_id!r} operator message is invalid"
                )
            request_id = message.get("request_id")
            action = message.get("action")
            instruction = message.get("instruction")
            sent_at = message.get("sent_at")
            applied_iteration = message.get("applied_iteration")
            applied_at = message.get("applied_at")
            if (
                not isinstance(request_id, str)
                or action not in {"guide", "revise"}
                or not isinstance(instruction, str)
                or not isinstance(sent_at, str)
                or (
                    applied_iteration is not None
                    and not isinstance(applied_iteration, int)
                )
                or (applied_at is not None and not isinstance(applied_at, str))
            ):
                raise RuntimeSourceError(
                    f"session {session_id!r} operator message is invalid"
                )
            records.append(
                {
                    "request_id": request_id,
                    "action": action,
                    "instruction": instruction,
                    "sent_at": sent_at,
                    "applied_iteration": applied_iteration,
                    "applied_at": applied_at,
                }
            )
        return records

    def control(
        self,
        session_id: str,
        *,
        request_id: str,
        action: str,
        instruction: str | None,
        expected_sequence: int,
    ) -> dict[str, Any]:
        """Send one authenticated directive to the selected agent process."""
        session = self.session(session_id)
        if session is None:
            raise RuntimeSourceError(f"unknown runtime session {session_id!r}")
        if not session.live:
            raise RuntimeSourceError("the selected session is not live")
        if expected_sequence != session.latest_seq:
            raise RuntimeSourceError(
                "the selected session advanced, refresh before controlling it"
            )
        if not session.control_available:
            raise RuntimeSourceError(
                "the selected session has no available operator endpoint"
            )
        session_dir = self._session_dir(session_id)
        manifest = self._object(session_dir / "session.json")
        digest = hashlib.sha256(session_id.encode()).hexdigest()[:20]
        expected_socket = (
            Path(tempfile.gettempdir())
            / f"boukensha-{digest}-operator.sock"
        )
        socket_value = manifest.get("operator_socket")
        if socket_value != str(expected_socket):
            raise RuntimeSourceError(
                "the selected session has no valid operator endpoint"
            )
        token_path = session_dir / "control.token"
        try:
            token = token_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise RuntimeSourceError(
                "the selected session control token is unavailable"
            ) from error
        request = {
            "protocol_version": 1,
            "request_id": request_id,
            "action": action,
            "instruction": instruction,
            "expected_sequence": expected_sequence,
            "player_id": session.player_id,
            "session_id": session.id,
            "token": token,
        }
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(str(expected_socket))
                client.sendall(
                    (json.dumps(request, sort_keys=True) + "\n").encode()
                )
                response = client.recv(65_536)
        except OSError as error:
            raise RuntimeSourceError(
                "the selected agent control endpoint is unavailable"
            ) from error
        try:
            value = json.loads(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RuntimeSourceError(
                "the selected agent returned an invalid control receipt"
            ) from error
        if not isinstance(value, dict):
            raise RuntimeSourceError(
                "the selected agent returned an invalid control receipt"
            )
        if value.get("ok") is not True:
            raise RuntimeSourceError(
                str(value.get("error") or "the agent rejected control")
            )
        return value

    def recover_knowledge(
        self,
        session_id: str,
        *,
        player_id: str,
        action: str,
        expected_sequence: int,
        snapshot_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        """Use only the selected authenticated gateway session's authority."""

        session = self.session(session_id)
        if session is None:
            raise RuntimeSourceError(f"unknown runtime session {session_id!r}")
        if session.player_id != player_id:
            raise RuntimeSourceError(
                "selected session does not belong to the selected player"
            )
        if not session.live:
            raise RuntimeSourceError("the selected session is not live")
        if session.control_state is None:
            raise RuntimeSourceError(
                "the selected session has no knowledge recovery endpoint"
            )
        if expected_sequence != session.latest_seq:
            raise RuntimeSourceError(
                "the selected session advanced, refresh before controlling it"
            )
        directory = self._session_dir(session_id)
        if action == "reset":
            receipt = request_reset(
                directory,
                expected_sequence=expected_sequence,
            )
        elif action == "restore":
            if not snapshot_id:
                raise RuntimeSourceError("restore requires a snapshot identity")
            receipt = request_knowledge_restore(
                directory,
                snapshot_id=snapshot_id,
                reason=reason,
                expected_sequence=expected_sequence,
            )
        else:
            raise RuntimeSourceError("unsupported knowledge recovery action")
        if receipt.get("ok") is not True:
            raise RuntimeSourceError(
                str(receipt.get("error") or "knowledge recovery was rejected")
            )
        return receipt

    def _session(
        self, row: sqlite3.Row, root: Path | None = None
    ) -> RuntimeSession:
        session_dir = self._safe_session_dir(
            str(row["session_id"]),
            str(row["player_id"]),
            Path(str(row["session_dir"])),
            root,
        )
        control_state = self._control_state(session_dir)
        control_available = self._operator_available(
            session_dir,
            str(row["session_id"]),
            str(row["state"]),
        )
        journal = session_dir / "gateway.db"
        count, latest = self._journal_summary(journal)
        objective, goal_count, nudge_count = self._objective_summary(session_dir)
        return RuntimeSession(
            id=str(row["session_id"]),
            player_id=str(row["player_id"]),
            character=str(row["character"]),
            gateway_session_id=str(row["gateway_session_id"]),
            state=str(row["state"]),
            control_state=control_state,
            control_available=control_available,
            capture_status=str(row["capture_status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            ended_at=(
                None if row["ended_at"] is None else str(row["ended_at"])
            ),
            stop_mode=(
                None if row["stop_mode"] is None else str(row["stop_mode"])
            ),
            event_count=count,
            latest_seq=latest,
            legacy=bool(row["legacy"]),
            pid=None if row["pid"] is None else int(row["pid"]),
            objective=objective,
            goal_count=goal_count,
            nudge_count=nudge_count,
        )

    def _objective_summary(
        self,
        session_dir: Path,
    ) -> tuple[str | None, int, int]:
        """Read the current applied objective and operator-message counts."""
        source = session_dir / "operator-messages.json"
        messages: list[dict[str, Any]] = []
        if source.is_file():
            try:
                value = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                value = None
            raw = value.get("messages") if isinstance(value, dict) else None
            if isinstance(raw, list):
                messages = [
                    message
                    for message in raw
                    if isinstance(message, dict)
                    and isinstance(message.get("instruction"), str)
                    and message.get("action") in {"guide", "revise"}
                    and isinstance(message.get("applied_at"), str)
                ]
        initial = self._initial_objective(session_dir / "agent.jsonl")
        revisions = [
            str(message["instruction"]).strip()
            for message in messages
            if message.get("action") == "revise"
            and str(message["instruction"]).strip()
        ]
        nudges = sum(message.get("action") == "guide" for message in messages)
        objective = revisions[-1] if revisions else initial
        goal_count = (1 if initial is not None else 0) + len(revisions)
        return objective, goal_count, nudges

    @staticmethod
    def _initial_objective(source: Path) -> str | None:
        """Recover an authored initial objective without treating nudges as goals."""
        if not source.is_file():
            return None
        try:
            raw = source.read_bytes()
            text = raw[: raw.rfind(b"\n") + 1].decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        first_turn: str | None = None
        for line in text.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("phase") == "session_start":
                value = event.get("objective")
                title = value.get("title") if isinstance(value, dict) else None
                if isinstance(title, str) and title.strip():
                    return title.strip()
            if event.get("phase") == "turn" and first_turn is None:
                instruction = event.get("instruction")
                if isinstance(instruction, str) and instruction.strip():
                    first_turn = instruction.strip()
        return first_turn

    @staticmethod
    def _session_query(database: sqlite3.Connection, tail: str) -> str:
        """Select every row field one session is derived from.

        A registry written before stop_mode existed has no such column,
        and reads as a session that never named how it stopped.
        """
        columns = {
            str(row["name"])
            for row in database.execute("PRAGMA table_info(sessions)")
        }
        stop_mode = (
            "stop_mode" if "stop_mode" in columns else "NULL AS stop_mode"
        )
        return (
            "SELECT session_id, player_id, character, gateway_session_id, "
            "state, capture_status, created_at, updated_at, ended_at, "
            f"{stop_mode}, legacy, session_dir, pid FROM sessions {tail}"
        )

    def _locate(self, session_id: str) -> tuple[sqlite3.Row, Path] | None:
        """Find one registry row and the directory it is allowed to own."""
        for root in self._roots():
            registry = root / "registry.db"
            if not registry.is_file():
                continue
            try:
                with self._database(registry) as database:
                    row = database.execute(
                        "SELECT session_id, player_id, session_dir, state, pid "
                        "FROM sessions WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
            except sqlite3.Error as error:
                raise RuntimeSourceError(
                    "runtime registry is unreadable"
                ) from error
            if row is None:
                continue
            return row, self._safe_session_dir(
                str(row["session_id"]),
                str(row["player_id"]),
                Path(str(row["session_dir"])),
                root,
            )
        return None

    def _session_dir(self, session_id: str) -> Path:
        if not self._roots():
            raise RuntimeSourceError("runtime registry is unavailable")
        located = self._locate(session_id)
        if located is None:
            raise RuntimeSourceError(f"unknown runtime session {session_id!r}")
        return located[1]

    def _safe_session_dir(
        self,
        session_id: str,
        player_id: str,
        path: Path,
        root: Path | None = None,
    ) -> Path:
        resolved = path.expanduser().resolve()
        expected = (
            (root or self.config_dir)
            / "profiles"
            / player_id
            / "sessions"
            / session_id
        ).resolve()
        if resolved != expected:
            raise RuntimeSourceError(
                f"session {session_id!r} path violates the runtime layout"
            )
        return resolved

    @staticmethod
    def _object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeSourceError(f"{path.name} is unreadable") from error
        if not isinstance(value, dict):
            raise RuntimeSourceError(f"{path.name} is not an object")
        return value

    @staticmethod
    def _control_state(session_dir: Path) -> str | None:
        states: list[str] = []
        for name in ("operator-state.json", "control-state.json"):
            projection = session_dir / name
            if not projection.is_file():
                continue
            try:
                value = json.loads(projection.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                states.append("capture_gap")
                continue
            state = value.get("state") if isinstance(value, dict) else None
            states.append(
                state if isinstance(state, str) else "capture_gap"
            )
        for priority in (
            "capture_gap",
            "quarantined",
            "stopped",
            "paused",
            "draining",
            "running",
        ):
            if priority in states:
                return priority
        return states[0] if states else None

    @staticmethod
    def _operator_available(
        session_dir: Path,
        session_id: str,
        lifecycle: str,
    ) -> bool:
        if lifecycle not in {"starting", "running", "draining"}:
            return False
        try:
            manifest = json.loads(
                (session_dir / "session.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(manifest, dict):
            return False
        digest = hashlib.sha256(session_id.encode()).hexdigest()[:20]
        expected = (
            Path(tempfile.gettempdir())
            / f"boukensha-{digest}-operator.sock"
        )
        return (
            manifest.get("operator_socket") == str(expected)
            and expected.is_socket()
            and (session_dir / "control.token").is_file()
        )

    @classmethod
    def _journal_summary(cls, journal: Path) -> tuple[int, int]:
        if not journal.is_file():
            return 0, 0
        try:
            with cls._database(journal) as database:
                row = database.execute(
                    "SELECT COUNT(*) AS count, "
                    "COALESCE(MAX(seq), 0) AS latest FROM events"
                ).fetchone()
        except sqlite3.Error:
            return 0, 0
        return int(row["count"]), int(row["latest"])

    @staticmethod
    @contextmanager
    def _database(path: Path) -> Iterator[sqlite3.Connection]:
        database = sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
            timeout=1,
        )
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA query_only=ON")
        try:
            yield database
        finally:
            database.close()
