"""Read registered player sessions and their journals without taking ownership."""

from __future__ import annotations

import hashlib
import json
import socket
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mud_gateway.journal import Event
from mud_gateway.reset_client import (
    request_knowledge_restore,
    request_reset,
)

from ..errors import (
    ObservatoryRepositoryError,
    PathIdentityError,
    SourceUnavailableError,
)
from ..models import GatewayEventRecord, SessionRecord
from ..repositories import (
    AgentRepository,
    ControlRepository,
    EventRepository,
    LifecycleRepository,
    OperatorRepository,
    RegistryDatabase,
    SessionCatalogRepository,
    SessionLookupRepository,
)


class RuntimeSourceError(RuntimeError):
    """The local runtime registry or one selected journal cannot be read."""


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
    objective: str | None
    goal_count: int
    nudge_count: int

    @property
    def live(self) -> bool:
        return self.state in {
            "starting",
            "running",
            "draining",
            "quarantined",
        }

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


class RuntimeSource:
    """Discover all players and sessions from the launcher registry."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir.expanduser().resolve()
        self.registry = self.config_dir / "registry.db"
        self._registry = (
            RegistryDatabase(self.config_dir) if self.registry.is_file() else None
        )
        self._catalog = (
            None if self._registry is None else SessionCatalogRepository(self._registry)
        )
        self._lookup = (
            None if self._registry is None else SessionLookupRepository(self._registry)
        )
        self._lifecycle = (
            None if self._registry is None else LifecycleRepository(self._registry)
        )
        self._control = ControlRepository()
        self._event_repositories: dict[str, EventRepository] = {}

    @property
    def available(self) -> bool:
        return self.registry.is_file()

    def sessions(self) -> tuple[RuntimeSession, ...]:
        if self._catalog is None:
            return ()
        try:
            records: list[SessionRecord] = []
            while True:
                page = self._catalog.page(
                    offset=len(records),
                    limit=500,
                )
                records.extend(page)
                if len(page) < 500:
                    break
        except PathIdentityError as error:
            raise RuntimeSourceError(
                "session path violates the runtime layout"
            ) from error
        except ObservatoryRepositoryError as error:
            raise RuntimeSourceError("runtime registry is unreadable") from error
        return tuple(self._session(record) for record in records)

    def session(self, session_id: str) -> RuntimeSession | None:
        if self._lookup is None:
            return None
        try:
            record = self._lookup.get(session_id)
        except PathIdentityError as error:
            raise RuntimeSourceError(
                f"session {session_id!r} path violates the runtime layout"
            ) from error
        except ObservatoryRepositoryError as error:
            raise RuntimeSourceError("runtime registry is unreadable") from error
        return None if record is None else self._session(record)

    def events(
        self,
        session_id: str,
        *,
        after: int = 0,
        through: int | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        record = self._session_record(session_id)
        journal = record.session_dir / "gateway.db"
        if not journal.is_file() or journal.stat().st_size == 0:
            return []
        try:
            repository = self._event_repository(record)
        except SourceUnavailableError:
            return []
        try:
            records: list[GatewayEventRecord] = []
            cursor = after
            remaining = limit
            while remaining is None or remaining > 0:
                page_limit = 2_000 if remaining is None else min(remaining, 2_000)
                page = repository.page(
                    after=cursor,
                    through=through,
                    limit=page_limit,
                )
                records.extend(page)
                if len(page) < page_limit:
                    break
                cursor = page[-1].sequence
                if through is not None and cursor >= through:
                    break
                if remaining is not None:
                    remaining -= len(page)
        except ObservatoryRepositoryError as error:
            raise RuntimeSourceError(
                f"session {session_id!r} journal is unreadable"
            ) from error
        return [
            Event(
                seq=record.sequence,
                session=record.session_id,
                at=record.at,
                monotonic=record.monotonic,
                kind=record.kind,
                payload=record.payload,
                trace_id=record.trace_id,
            )
            for record in records
        ]

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

    def agent_events(self, session_id: str) -> list[dict[str, Any]]:
        record = self._session_record(session_id)
        repository = AgentRepository(record)
        records: list[dict[str, Any]] = []
        offset = 0
        line = 1
        try:
            while True:
                page = repository.page(
                    offset=offset,
                    start_line=line,
                    limit=1_000,
                )
                records.extend(page.records)
                if page.incomplete_tail or not page.records:
                    break
                offset = page.next_offset
                line = page.next_line
        except ObservatoryRepositoryError as error:
            raise RuntimeSourceError(
                f"session {session_id!r} agent log is unreadable"
            ) from error
        return records

    def operator_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Read the agent-owned durable operator message history."""
        record = self._session_record(session_id)
        try:
            return list(OperatorRepository(record).messages(limit=1_000))
        except ObservatoryRepositoryError as error:
            raise RuntimeSourceError(
                f"session {session_id!r} operator message history is invalid"
            ) from error

    def lifecycle(self, session_id: str) -> list[dict[str, Any]]:
        """Read bounded launcher lifecycle evidence for one selected session."""
        if self._lifecycle is None:
            return []
        self._session_record(session_id)
        try:
            records = self._lifecycle.page(session_id, limit=1_000)
        except ObservatoryRepositoryError as error:
            raise RuntimeSourceError(
                f"session {session_id!r} lifecycle is unreadable"
            ) from error
        return [
            {
                "sequence": record.sequence,
                "session_id": record.session_id,
                "at": record.at,
                "state": record.state,
                "detail": record.detail,
            }
            for record in records
        ]

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
            Path(tempfile.gettempdir()) / f"boukensha-{digest}-operator.sock"
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
                client.sendall((json.dumps(request, sort_keys=True) + "\n").encode())
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
        return dict(receipt)

    def _session(self, record: SessionRecord) -> RuntimeSession:
        session_dir = record.session_dir
        control = self._control.status(record)
        journal = session_dir / "gateway.db"
        count, latest = self._journal_summary(journal)
        objective, goal_count, nudge_count = self._objective_summary(record)
        return RuntimeSession(
            id=record.session_id,
            player_id=record.player_id,
            character=record.character,
            gateway_session_id=record.gateway_session_id,
            state=record.state,
            control_state=control.state,
            control_available=control.available,
            capture_status=record.capture_status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            ended_at=record.ended_at,
            stop_mode=record.stop_mode,
            event_count=count,
            latest_seq=latest,
            legacy=record.legacy,
            objective=objective,
            goal_count=goal_count,
            nudge_count=nudge_count,
        )

    def _objective_summary(
        self,
        record: SessionRecord,
    ) -> tuple[str | None, int, int]:
        """Read the current applied objective and operator-message counts."""
        try:
            retained = OperatorRepository(record).messages(limit=1_000)
        except ObservatoryRepositoryError:
            retained = ()
        messages = [
            message
            for message in retained
            if isinstance(message.get("applied_at"), str)
        ]
        initial = self._initial_objective(record.session_dir / "agent.jsonl")
        revisions = [
            str(message["instruction"]).strip()
            for message in messages
            if message.get("action") == "revise" and str(message["instruction"]).strip()
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
            lines = source.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        first_turn: str | None = None
        for line in lines:
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

    def _session_dir(self, session_id: str) -> Path:
        return self._session_record(session_id).session_dir

    def _session_record(self, session_id: str) -> SessionRecord:
        if self._lookup is None:
            raise RuntimeSourceError("runtime registry is unavailable")
        try:
            record = self._lookup.get(session_id)
        except PathIdentityError as error:
            raise RuntimeSourceError(
                f"session {session_id!r} path violates the runtime layout"
            ) from error
        except ObservatoryRepositoryError as error:
            raise RuntimeSourceError("runtime registry is unreadable") from error
        if record is None:
            raise RuntimeSourceError(f"unknown runtime session {session_id!r}")
        return record

    def _event_repository(
        self,
        record: SessionRecord,
    ) -> EventRepository:
        repository = self._event_repositories.get(record.session_id)
        if repository is None:
            repository = EventRepository(record)
            self._event_repositories[record.session_id] = repository
        return repository

    @staticmethod
    def _object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeSourceError(f"{path.name} is unreadable") from error
        if not isinstance(value, dict):
            raise RuntimeSourceError(f"{path.name} is not an object")
        return value

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
