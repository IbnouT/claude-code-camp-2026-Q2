"""Typed loopback API that starts launcher-owned agent sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal

ResetMode = Literal["none", "temple", "baseline"]
StopMode = Literal["cooperative", "forced_after_grace"]
PLAYER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,127}$")
START_PATH = "/api/sessions/start"
STOP_PATH = re.compile(r"^/api/sessions/([^/]+)/stop$")
START_TIMEOUT_SECONDS = 55.0
STOP_GRACE_SECONDS = 10.0
STOP_FORCE_SECONDS = 3.0
ACTIVE_STATES = frozenset({"starting", "running", "draining", "quarantined"})
TERMINAL_STATES = frozenset({"stopped", "crashed"})
ALLOWED_ORIGINS = frozenset({
    "http://127.0.0.1:8787",
    "http://localhost:8787",
    "http://127.0.0.1:8791",
    "http://localhost:8791",
})


class StartRequestError(ValueError):
    """A start request is malformed or cannot be fulfilled."""

    def __init__(self, code: str, detail: str, status: HTTPStatus) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


class StopRequestError(ValueError):
    """A stop request is malformed or cannot be fulfilled safely."""

    def __init__(self, code: str, detail: str, status: HTTPStatus) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class StartRequest:
    """One public start-session request."""

    player_id: str
    reset: ResetMode

    @classmethod
    def decode(cls, value: object) -> "StartRequest":
        if not isinstance(value, dict):
            raise StartRequestError(
                "invalid_request",
                "Request body must be a JSON object.",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        unknown = set(value) - {"player_id", "reset"}
        if unknown:
            raise StartRequestError(
                "invalid_request",
                f"Unknown request fields: {', '.join(sorted(unknown))}.",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        player_id = value.get("player_id")
        reset = value.get("reset")
        if not isinstance(player_id, str) or not PLAYER_ID.fullmatch(player_id):
            raise StartRequestError(
                "invalid_player",
                "player_id is missing or invalid.",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        if reset not in {"none", "temple", "baseline"}:
            raise StartRequestError(
                "invalid_reset",
                "reset must be none, temple, or baseline.",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        return cls(player_id=player_id, reset=reset)


@dataclass(frozen=True)
class StopResult:
    """One terminal receipt for a supervised session."""

    session_id: str
    player_id: str
    state: Literal["stopped"]
    mode: StopMode

    def public(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "player_id": self.player_id,
            "state": self.state,
            "mode": self.mode,
        }


class Supervisor:
    """Own background launcher processes and return their runtime identities."""

    def __init__(self, repository_root: Path, config_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.config_root = config_root.resolve()
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.Lock()

    def start(self, request: StartRequest) -> str:
        with self._lock:
            before = set(self._session_ids(request.player_id))
            command = [
                "uv",
                "run",
                "--project",
                str(self.repository_root / "week2_capable" / "agent"),
                "boukensha",
                "--no-tui",
                "--player-profile",
                request.player_id,
            ]
            if request.reset == "baseline":
                command.extend(("--reset-baseline", "level1-temple@1"))
            elif request.reset == "temple":
                command.append("--relocate-temple")
            environment = dict(os.environ)
            environment["BOUKENSHA_DIR"] = str(self.config_root)
            process = subprocess.Popen(
                command,
                cwd=self.repository_root,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                session_id = self._wait_for_ready(
                    process,
                    player_id=request.player_id,
                    reset=request.reset,
                    before=before,
                )
            except Exception:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
                raise
            self.processes[session_id] = process
            return session_id

    def stop(self, session_id: str) -> StopResult:
        """Stop one owned runtime without affecting any other process group."""

        if not SESSION_ID.fullmatch(session_id):
            raise StopRequestError(
                "invalid_session",
                "The session identity is invalid.",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        with self._lock:
            row = self._session(session_id)
            if row is None:
                raise StopRequestError(
                    "session_not_found",
                    "The selected session does not exist.",
                    HTTPStatus.NOT_FOUND,
                )
            player_id = str(row["player_id"])
            state = str(row["state"])
            retained_mode = row["stop_mode"]
            if state in TERMINAL_STATES and retained_mode in {
                "cooperative",
                "forced_after_grace",
            }:
                return StopResult(
                    session_id=session_id,
                    player_id=player_id,
                    state="stopped",
                    mode=retained_mode,
                )
            if state not in ACTIVE_STATES:
                raise StopRequestError(
                    "session_not_live",
                    "The selected session is not running.",
                    HTTPStatus.CONFLICT,
                )
            process = self.processes.get(session_id)
            if process is None:
                raise StopRequestError(
                    "supervisor_mismatch",
                    "The selected session is not owned by this supervisor instance.",
                    HTTPStatus.CONFLICT,
                )

            self._request_operator_stop(row)
            self._transition(
                session_id,
                "draining",
                {"reason": "operator_stop_requested"},
            )
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()

            mode: StopMode = "cooperative"
            if not _wait_for_exit(process, STOP_GRACE_SECONDS):
                mode = "forced_after_grace"
                child_pid = int(row["pid"])
                if not _is_owned_child(process.pid, child_pid):
                    raise StopRequestError(
                        "runtime_identity_mismatch",
                        "The child process identity could not be verified.",
                        HTTPStatus.CONFLICT,
                    )
                os.killpg(child_pid, signal.SIGTERM)
                if not _wait_for_exit(process, STOP_FORCE_SECONDS):
                    os.killpg(child_pid, signal.SIGKILL)
                    if not _wait_for_exit(process, STOP_FORCE_SECONDS):
                        raise StopRequestError(
                            "stop_timeout",
                            "The verified process group did not stop.",
                            HTTPStatus.GATEWAY_TIMEOUT,
                        )

            self._terminal(session_id, mode)
            self.processes.pop(session_id, None)
            return StopResult(
                session_id=session_id,
                player_id=player_id,
                state="stopped",
                mode=mode,
            )

    def _wait_for_ready(
        self,
        process: subprocess.Popen[bytes],
        *,
        player_id: str,
        reset: ResetMode,
        before: set[str],
    ) -> str:
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                detail = _process_error(process)
                code = (
                    "player_live"
                    if "already running" in detail.casefold()
                    else "launch_failure"
                )
                status = (
                    HTTPStatus.CONFLICT
                    if code == "player_live"
                    else HTTPStatus.BAD_GATEWAY
                )
                raise StartRequestError(code, detail, status)
            candidates = [
                row
                for row in self._sessions(player_id)
                if row["session_id"] not in before
                and row["state"] == "running"
            ]
            if candidates:
                session_id = str(candidates[-1]["session_id"])
                session_dir = Path(str(candidates[-1]["session_dir"]))
                if self._ready(session_dir, reset):
                    return session_id
            time.sleep(0.1)
        raise StartRequestError(
            "launch_timeout",
            "The agent did not become ready before the start timeout.",
            HTTPStatus.GATEWAY_TIMEOUT,
        )

    @staticmethod
    def _ready(session_dir: Path, reset: ResetMode) -> bool:
        control_state = session_dir / "control-state.json"
        if not control_state.is_file():
            return False
        try:
            state = json.loads(control_state.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(state, dict) or state.get("state") != "running":
            return False
        if reset == "none":
            return True
        kind = "reset_receipt" if reset == "baseline" else "relocation_receipt"
        journal = session_dir / "gateway.db"
        try:
            with sqlite3.connect(f"file:{journal.resolve()}?mode=ro", uri=True) as db:
                row = db.execute(
                    "SELECT payload FROM events WHERE kind = ? "
                    "ORDER BY seq DESC LIMIT 1",
                    (kind,),
                ).fetchone()
        except sqlite3.Error:
            return False
        if row is None:
            return False
        try:
            receipt = json.loads(row[0])
        except json.JSONDecodeError:
            return False
        if receipt.get("ok") is not True:
            raise StartRequestError(
                "reset_failure",
                str(receipt.get("error") or f"{reset} reset did not verify."),
                HTTPStatus.CONFLICT,
            )
        return True

    def _session_ids(self, player_id: str) -> list[str]:
        return [str(row["session_id"]) for row in self._sessions(player_id)]

    def _session(self, session_id: str) -> sqlite3.Row | None:
        path = self.config_root / "registry.db"
        if not path.is_file():
            return None
        with sqlite3.connect(path) as database:
            database.row_factory = sqlite3.Row
            self._ensure_stop_mode(database)
            return database.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

    def _sessions(self, player_id: str) -> list[sqlite3.Row]:
        path = self.config_root / "registry.db"
        if not path.is_file():
            return []
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            return list(
                db.execute(
                    "SELECT session_id, session_dir, state, created_at "
                    "FROM sessions WHERE player_id = ? "
                    "ORDER BY created_at, session_id",
                    (player_id,),
                )
            )

    def _request_operator_stop(self, row: sqlite3.Row) -> None:
        session_id = str(row["session_id"])
        player_id = str(row["player_id"])
        session_dir = self._safe_session_dir(row)
        digest = hashlib.sha256(session_id.encode()).hexdigest()[:20]
        operator_socket = (
            Path(tempfile.gettempdir())
            / f"boukensha-{digest}-operator.sock"
        )
        try:
            manifest = json.loads(
                (session_dir / "session.json").read_text(encoding="utf-8")
            )
            token = (
                session_dir / "control.token"
            ).read_text(encoding="utf-8").strip()
        except (OSError, json.JSONDecodeError) as error:
            raise StopRequestError(
                "control_unavailable",
                "The authenticated stop endpoint is unavailable.",
                HTTPStatus.CONFLICT,
            ) from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("session_id") != session_id
            or manifest.get("player_id") != player_id
            or manifest.get("operator_socket") != str(operator_socket)
            or not operator_socket.is_socket()
        ):
            raise StopRequestError(
                "runtime_identity_mismatch",
                "The selected runtime identity could not be verified.",
                HTTPStatus.CONFLICT,
            )
        request = {
            "protocol_version": 1,
            "request_id": f"stop-{uuid.uuid4()}",
            "action": "stop",
            "instruction": None,
            "expected_sequence": self._latest_sequence(session_dir),
            "player_id": player_id,
            "session_id": session_id,
            "token": token,
        }
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(str(operator_socket))
                client.sendall(
                    (json.dumps(request, sort_keys=True) + "\n").encode()
                )
                response = client.recv(65_536)
            receipt = json.loads(response)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise StopRequestError(
                "control_unavailable",
                "The authenticated stop request did not return a receipt.",
                HTTPStatus.CONFLICT,
            ) from error
        if not isinstance(receipt, dict) or receipt.get("ok") is not True:
            detail = (
                receipt.get("error")
                if isinstance(receipt, dict)
                else "invalid control receipt"
            )
            raise StopRequestError(
                "control_rejected",
                str(detail),
                HTTPStatus.CONFLICT,
            )

    def _safe_session_dir(self, row: sqlite3.Row) -> Path:
        session_id = str(row["session_id"])
        player_id = str(row["player_id"])
        actual = Path(str(row["session_dir"])).expanduser().resolve()
        expected = (
            self.config_root
            / "profiles"
            / player_id
            / "sessions"
            / session_id
        ).resolve()
        if actual != expected:
            raise StopRequestError(
                "runtime_identity_mismatch",
                "The selected runtime path could not be verified.",
                HTTPStatus.CONFLICT,
            )
        return actual

    @staticmethod
    def _latest_sequence(session_dir: Path) -> int:
        try:
            with sqlite3.connect(
                f"file:{(session_dir / 'gateway.db').resolve()}?mode=ro",
                uri=True,
            ) as database:
                row = database.execute(
                    "SELECT COALESCE(MAX(seq), 0) FROM events"
                ).fetchone()
        except sqlite3.Error:
            return 0
        return int(row[0]) if row is not None else 0

    def _transition(
        self,
        session_id: str,
        state: str,
        detail: dict[str, str],
    ) -> None:
        now = _now()
        with sqlite3.connect(self.config_root / "registry.db") as database:
            self._ensure_stop_mode(database)
            database.execute(
                "UPDATE sessions SET state = ?, updated_at = ? "
                "WHERE session_id = ?",
                (state, now, session_id),
            )
            database.execute(
                "INSERT INTO lifecycle (session_id, at, state, detail) "
                "VALUES (?, ?, ?, ?)",
                (session_id, now, state, json.dumps(detail, sort_keys=True)),
            )

    def _terminal(self, session_id: str, mode: StopMode) -> None:
        now = _now()
        detail = json.dumps({"stop_mode": mode}, sort_keys=True)
        with sqlite3.connect(self.config_root / "registry.db") as database:
            self._ensure_stop_mode(database)
            database.execute(
                "UPDATE sessions SET state = 'stopped', updated_at = ?, "
                "ended_at = COALESCE(ended_at, ?), stop_mode = ? "
                "WHERE session_id = ?",
                (now, now, mode, session_id),
            )
            database.execute(
                "INSERT INTO lifecycle (session_id, at, state, detail) "
                "VALUES (?, ?, 'stopped', ?)",
                (session_id, now, detail),
            )

    @staticmethod
    def _ensure_stop_mode(database: sqlite3.Connection) -> None:
        columns = {
            str(row[1])
            for row in database.execute("PRAGMA table_info(sessions)")
        }
        if "stop_mode" not in columns:
            database.execute("ALTER TABLE sessions ADD COLUMN stop_mode TEXT")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wait_for_exit(
    process: subprocess.Popen[bytes],
    timeout: float,
) -> bool:
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


def _is_owned_child(launcher_pid: int, child_pid: int) -> bool:
    if launcher_pid <= 0 or child_pid <= 0:
        return False
    try:
        group = os.getpgid(child_pid)
        parent = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(child_pid)],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return group == child_pid and parent == str(launcher_pid)


def _process_error(process: subprocess.Popen[bytes]) -> str:
    stderr = b"" if process.stderr is None else process.stderr.read(16_384)
    text = stderr.decode(errors="replace").strip()
    return text.splitlines()[-1] if text else "The agent launcher exited."


class Handler(BaseHTTPRequestHandler):
    """Serve typed session lifecycle operations over loopback."""

    supervisor: Supervisor

    def do_POST(self) -> None:
        if not self._origin_allowed():
            self._json(
                HTTPStatus.FORBIDDEN,
                {
                    "error": "origin_rejected",
                    "detail": "The request origin is not allowed.",
                },
            )
            return
        stop_match = STOP_PATH.fullmatch(self.path)
        if stop_match is not None:
            self._stop(stop_match.group(1))
            return
        if self.path == START_PATH:
            self._start()
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_OPTIONS(self) -> None:
        if not self._origin_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"error": "origin_rejected"})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.send_header("access-control-allow-methods", "POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.end_headers()

    def _start(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > 16_384:
                raise StartRequestError(
                    "invalid_request",
                    "Request body is missing or too large.",
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise StartRequestError(
                    "invalid_json",
                    "Request body is not valid JSON.",
                    HTTPStatus.BAD_REQUEST,
                ) from error
            request = StartRequest.decode(body)
            session_id = self.supervisor.start(request)
        except StartRequestError as error:
            self._json(
                error.status,
                {"error": error.code, "detail": error.detail},
            )
            return
        except Exception:
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "launch_failure",
                    "detail": "The local launcher failed unexpectedly.",
                },
            )
            return
        self._json(
            HTTPStatus.CREATED,
            {
                "session_id": session_id,
                "player_id": request.player_id,
                "reset": request.reset,
                "state": "running",
            },
        )

    def _stop(self, session_id: str) -> None:
        try:
            result = self.supervisor.stop(session_id)
        except StopRequestError as error:
            self._json(
                error.status,
                {"error": error.code, "detail": error.detail},
            )
            return
        except Exception:
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "stop_failure",
                    "detail": "The local supervisor failed unexpectedly.",
                },
            )
            return
        self._json(HTTPStatus.OK, result.public())

    def log_message(self, format: str, *args: object) -> None:
        return

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("origin")
        return origin is None or origin in ALLOWED_ORIGINS

    def _cors(self) -> None:
        origin = self.headers.get("origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("access-control-allow-origin", origin)
            self.send_header("vary", "origin")

    def _json(self, status: HTTPStatus, value: object) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self._cors()
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    config_root = Path(
        os.environ.get("BOUKENSHA_DIR", repository_root / ".boukensha")
    )
    Handler.supervisor = Supervisor(repository_root, config_root)
    server = ThreadingHTTPServer(("127.0.0.1", 8792), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
