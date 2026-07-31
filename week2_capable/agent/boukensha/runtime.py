"""Multi-player runtime identity, layout, registry, and process ownership."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import sqlite3
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

RUNTIME_ENV = {
    "player_id": "BOUKENSHA_PLAYER_ID",
    "agent_id": "BOUKENSHA_AGENT_ID",
    "session_id": "BOUKENSHA_SESSION_ID",
    "gateway_session_id": "BOUKENSHA_GATEWAY_SESSION_ID",
    "experiment_id": "BOUKENSHA_EXPERIMENT_ID",
    "run_id": "BOUKENSHA_RUN_ID",
    "session_dir": "BOUKENSHA_SESSION_DIR",
    "control_socket": "BOUKENSHA_CONTROL_SOCKET",
    "operator_socket": "BOUKENSHA_OPERATOR_SOCKET",
}

SAFE_ENV_NAMES = frozenset({
    "COLORTERM",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "NO_COLOR",
    "PATH",
    "SHELL",
    "TERM",
    "TMPDIR",
    "TZ",
})

REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    character TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    gateway_session_id TEXT NOT NULL,
    experiment_id TEXT,
    run_id TEXT,
    session_dir TEXT NOT NULL UNIQUE,
    manifest_path TEXT NOT NULL UNIQUE,
    control_socket TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    pid INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ended_at TEXT,
    exit_code INTEGER,
    stop_mode TEXT,
    capture_status TEXT NOT NULL DEFAULT 'complete',
    legacy INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_character
ON sessions(character)
WHERE state IN ('starting', 'running', 'draining', 'quarantined');
CREATE TABLE IF NOT EXISTS lifecycle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    at TEXT NOT NULL,
    state TEXT NOT NULL,
    detail TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);
"""


class RuntimeErrorBase(RuntimeError):
    """Base class for typed runtime failures."""


class CharacterAlreadyRunning(RuntimeErrorBase):
    """A live process already owns the selected character."""


class RuntimeIdentityError(RuntimeErrorBase):
    """The runtime identity envelope is missing or contradictory."""


@dataclass(frozen=True)
class RuntimeIdentity:
    """One immutable correlation envelope created by the launcher."""

    player_id: str
    character: str
    agent_id: str
    session_id: str
    gateway_session_id: str
    experiment_id: str | None = None
    run_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        player_id: str,
        character: str,
        experiment_id: str | None = None,
        run_id: str | None = None,
    ) -> "RuntimeIdentity":
        return cls(
            player_id=player_id,
            character=character,
            agent_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            gateway_session_id=str(uuid.uuid4()),
            experiment_id=experiment_id,
            run_id=run_id,
        )

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        character: str,
    ) -> "RuntimeIdentity | None":
        values = environment if environment is not None else os.environ
        present = {
            field: values.get(name)
            for field, name in RUNTIME_ENV.items()
            if field not in {
                "session_dir",
                "control_socket",
                "operator_socket",
            }
        }
        required = ("player_id", "agent_id", "session_id", "gateway_session_id")
        if not any(present.get(field) for field in required):
            return None
        missing = [field for field in required if not present.get(field)]
        if missing:
            raise RuntimeIdentityError(
                f"incomplete runtime identity, missing {', '.join(missing)}"
            )
        return cls(
            player_id=str(present["player_id"]),
            character=character,
            agent_id=str(present["agent_id"]),
            session_id=str(present["session_id"]),
            gateway_session_id=str(present["gateway_session_id"]),
            experiment_id=present.get("experiment_id"),
            run_id=present.get("run_id"),
        )

    def envelope(self) -> dict[str, str]:
        values = {
            "player_id": self.player_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "gateway_session_id": self.gateway_session_id,
        }
        if self.experiment_id:
            values["experiment_id"] = self.experiment_id
        if self.run_id:
            values["run_id"] = self.run_id
        return values


@dataclass(frozen=True)
class RuntimePaths:
    """Protected paths owned by one player session."""

    config_dir: Path
    profile_dir: Path
    session_dir: Path
    manifest: Path
    agent_log: Path
    gateway_journal: Path
    control_token: Path
    control_socket: Path
    operator_socket: Path

    @classmethod
    def for_identity(
        cls,
        config_dir: Path,
        identity: RuntimeIdentity,
    ) -> "RuntimePaths":
        profile = config_dir / "profiles" / identity.player_id
        session = profile / "sessions" / identity.session_id
        digest = hashlib.sha256(identity.session_id.encode()).hexdigest()[:20]
        socket = Path(tempfile.gettempdir()) / f"boukensha-{digest}.sock"
        operator = (
            Path(tempfile.gettempdir()) / f"boukensha-{digest}-operator.sock"
        )
        return cls(
            config_dir=config_dir,
            profile_dir=profile,
            session_dir=session,
            manifest=session / "session.json",
            agent_log=session / "agent.jsonl",
            gateway_journal=session / "gateway.db",
            control_token=session / "control.token",
            control_socket=socket,
            operator_socket=operator,
        )


class CharacterLock:
    """Stable file lock whose kernel ownership is the liveness authority."""

    def __init__(self, config_dir: Path, character: str) -> None:
        digest = hashlib.sha256(character.casefold().encode()).hexdigest()[:24]
        self.path = config_dir / "locks" / f"{digest}.lock"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self._handle: Any = None

    def acquire(self, identity: RuntimeIdentity) -> None:
        handle = self.path.open("a+", encoding="utf-8")
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.close()
            raise CharacterAlreadyRunning(
                f"character {identity.character!r} is already running"
            ) from error
        handle.seek(0)
        handle.truncate()
        json.dump(
            {
                "character": identity.character,
                "player_id": identity.player_id,
                "session_id": identity.session_id,
                "pid": os.getpid(),
            },
            handle,
            sort_keys=True,
        )
        handle.flush()
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


class SessionRegistry:
    """Launcher-owned registry with read-only discovery helpers."""

    def __init__(self, config_dir: Path) -> None:
        self.path = config_dir / "registry.db"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(REGISTRY_SCHEMA)
        self._db.commit()

    def register(
        self,
        identity: RuntimeIdentity,
        paths: RuntimePaths,
        *,
        state: str = "starting",
        legacy: bool = False,
    ) -> None:
        now = _now()
        try:
            self._db.execute(
                """
                INSERT INTO sessions (
                    session_id, player_id, character, agent_id,
                    gateway_session_id, experiment_id, run_id, session_dir,
                    manifest_path, control_socket, state, pid, created_at,
                    updated_at, legacy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity.session_id,
                    identity.player_id,
                    identity.character,
                    identity.agent_id,
                    identity.gateway_session_id,
                    identity.experiment_id,
                    identity.run_id,
                    str(paths.session_dir),
                    str(paths.manifest),
                    str(paths.control_socket),
                    state,
                    None if state in {"stopped", "crashed"} else os.getpid(),
                    now,
                    now,
                    int(legacy),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise CharacterAlreadyRunning(
                f"character {identity.character!r} is already registered live"
            ) from error
        self._append_lifecycle(identity.session_id, state, {})
        self._db.commit()

    def reconcile_character(self, character: str) -> list[str]:
        """Mark stale active rows after the caller acquired the character lock."""
        rows = self._db.execute(
            """
            SELECT session_id FROM sessions
            WHERE character = ?
              AND state IN ('starting', 'running', 'draining', 'quarantined')
            """,
            (character,),
        ).fetchall()
        reconciled = [str(row["session_id"]) for row in rows]
        for session_id in reconciled:
            self.transition(
                session_id,
                "crashed",
                detail={"reason": "orphan_reconciled_after_lock_acquisition"},
            )
        return reconciled

    def transition(
        self,
        session_id: str,
        state: str,
        *,
        detail: Mapping[str, Any] | None = None,
        exit_code: int | None = None,
    ) -> None:
        now = _now()
        ended = now if state in {"stopped", "crashed"} else None
        cursor = self._db.execute(
            """
            UPDATE sessions
            SET state = ?, updated_at = ?, ended_at = COALESCE(?, ended_at),
                exit_code = COALESCE(?, exit_code)
            WHERE session_id = ?
            """,
            (state, now, ended, exit_code, session_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeIdentityError(f"unknown session {session_id!r}")
        self._append_lifecycle(session_id, state, detail or {})
        self._db.commit()

    def sessions(self, *, player_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM sessions"
        args: tuple[Any, ...] = ()
        if player_id is not None:
            sql += " WHERE player_id = ?"
            args = (player_id,)
        sql += " ORDER BY created_at, session_id"
        return [dict(row) for row in self._db.execute(sql, args)]

    def session(self, session_id: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return None if row is None else dict(row)

    def close(self) -> None:
        self._db.close()

    def _append_lifecycle(
        self,
        session_id: str,
        state: str,
        detail: Mapping[str, Any],
    ) -> None:
        self._db.execute(
            "INSERT INTO lifecycle (session_id, at, state, detail) VALUES (?, ?, ?, ?)",
            (session_id, _now(), state, json.dumps(dict(detail), sort_keys=True)),
        )


class RuntimeSession:
    """One launcher-owned runtime allocation held for the process lifetime."""

    def __init__(
        self,
        identity: RuntimeIdentity,
        paths: RuntimePaths,
        registry: SessionRegistry,
        lock: CharacterLock,
    ) -> None:
        self.identity = identity
        self.paths = paths
        self.registry = registry
        self.lock = lock
        self._closed = False

    @classmethod
    def create(
        cls,
        config_dir: Path,
        *,
        player_id: str,
        character: str,
        experiment_id: str | None = None,
        run_id: str | None = None,
    ) -> "RuntimeSession":
        root = config_dir.expanduser().resolve()
        identity = RuntimeIdentity.create(
            player_id=player_id,
            character=character,
            experiment_id=experiment_id,
            run_id=run_id,
        )
        paths = RuntimePaths.for_identity(root, identity)
        lock = CharacterLock(root, character)
        lock.acquire(identity)
        registry = SessionRegistry(root)
        try:
            registry.reconcile_character(character)
            _create_runtime_paths(paths)
            _write_manifest(identity, paths)
            registry.register(identity, paths)
        except Exception:
            registry.close()
            lock.release()
            raise
        return cls(identity, paths, registry, lock)

    def child_environment(
        self,
        *,
        parent: Mapping[str, str],
        secrets: Mapping[str, str],
    ) -> dict[str, str]:
        environment = {
            name: value
            for name, value in parent.items()
            if name in SAFE_ENV_NAMES or name.startswith("LC_")
        }
        environment.update({key: value for key, value in secrets.items() if value})
        environment["BOUKENSHA_DIR"] = str(self.paths.config_dir)
        environment["BOUKENSHA_SESSION_DIR"] = str(self.paths.session_dir)
        environment["BOUKENSHA_CONTROL_SOCKET"] = str(self.paths.control_socket)
        environment["BOUKENSHA_OPERATOR_SOCKET"] = str(
            self.paths.operator_socket
        )
        for field, value in self.identity.envelope().items():
            environment[RUNTIME_ENV[field]] = value
        return environment

    def running(self, pid: int) -> None:
        self.registry._db.execute(
            "UPDATE sessions SET pid = ? WHERE session_id = ?",
            (pid, self.identity.session_id),
        )
        self.registry._db.commit()
        self.registry.transition(self.identity.session_id, "running")

    def close(self, *, exit_code: int = 0) -> None:
        if self._closed:
            return
        state = "stopped" if exit_code == 0 else "crashed"
        self.registry.transition(
            self.identity.session_id,
            state,
            exit_code=exit_code,
        )
        self.registry.close()
        self.lock.release()
        self._closed = True

    def terminate_process_group(self, pid: int, sig: int = signal.SIGTERM) -> None:
        os.killpg(pid, sig)


def identity_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a validated runtime envelope from an environment."""
    values = environment if environment is not None else os.environ
    envelope: dict[str, str] = {}
    for field, name in RUNTIME_ENV.items():
        value = values.get(name)
        if value:
            envelope[field] = value
    return envelope


def import_legacy_session(
    config_dir: Path,
    source: Path,
    *,
    player_id: str,
    character: str,
) -> RuntimeIdentity:
    """Copy one flat JSONL session into the versioned player layout."""
    root = config_dir.expanduser().resolve()
    original = source.expanduser().resolve()
    if not original.is_file():
        raise FileNotFoundError(original)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    namespace = uuid.UUID("62e71e4f-b772-4c0c-9317-a30fd3957adb")
    identity = RuntimeIdentity(
        player_id=player_id,
        character=character,
        agent_id=str(uuid.uuid5(namespace, f"agent:{original}:{digest}")),
        session_id=str(uuid.uuid5(namespace, f"session:{original}:{digest}")),
        gateway_session_id=str(uuid.uuid5(
            namespace,
            f"gateway:{original}:{digest}",
        )),
    )
    paths = RuntimePaths.for_identity(root, identity)
    registry = SessionRegistry(root)
    if paths.manifest.exists():
        registry.close()
        return identity
    try:
        paths.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(paths.profile_dir, 0o700)
        paths.session_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(paths.session_dir, 0o700)
        shutil.copy2(original, paths.agent_log)
        _write_manifest(
            identity,
            paths,
            extra={
                "legacy": True,
                "legacy_source": str(original),
                "legacy_digest": digest,
                "capture_gaps": [
                    "gateway_session_binding",
                    "gateway_journal",
                    "runtime_lifecycle",
                ],
            },
        )
        registry.register(identity, paths, state="stopped", legacy=True)
    except Exception:
        registry.close()
        raise
    registry.close()
    return identity


def _create_runtime_paths(paths: RuntimePaths) -> None:
    paths.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(paths.profile_dir, 0o700)
    paths.session_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(paths.session_dir, 0o700)
    token = uuid.uuid4().hex
    descriptor = os.open(
        paths.control_token,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(token)


def _write_manifest(
    identity: RuntimeIdentity,
    paths: RuntimePaths,
    *,
    extra: Mapping[str, Any] | None = None,
) -> None:
    settings = paths.config_dir / "settings.yaml"
    digest = hashlib.sha256(
        settings.read_bytes() if settings.is_file() else b""
    ).hexdigest()
    manifest = {
        "schema_version": 1,
        "layout_version": 1,
        **asdict(identity),
        "created_at": _now(),
        "configuration_digest": digest,
        "control_socket": str(paths.control_socket),
        "operator_socket": str(paths.operator_socket),
    }
    manifest.update(dict(extra or {}))
    temporary = paths.manifest.with_suffix(".tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(paths.manifest)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
