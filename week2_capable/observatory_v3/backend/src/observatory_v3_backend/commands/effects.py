"""Launcher and authenticated operator effects for durable commands."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Protocol

from ..sources.runtime import RuntimeSource, RuntimeSourceError
from .models import Command, CommandSubmission

#: Cooperative exit budget, then the escalation budget per signal.
STOP_GRACE_SECONDS = 10.0
STOP_FORCE_SECONDS = 3.0

# Seconds to wait for the launched agent to publish its session before the
# durable command is marked failed.
START_TIMEOUT_SECONDS = 55.0


def _agent_project() -> Path:
    """Locate the agent uv project, dev layout first, installed layout second."""
    parents = Path(__file__).resolve().parents
    direct = parents[5] / "agent"
    if (direct / "pyproject.toml").is_file():
        return direct
    return parents[6] / "week2_capable" / "agent"


def _reset_verified(session_dir: Path, reset: str) -> bool:
    """Return whether the requested reset produced a successful receipt.

    ``none`` needs no receipt. ``baseline`` and
    ``temple`` require a ``reset_receipt`` / ``relocation_receipt`` gateway event
    whose ``ok`` field is true. A receipt reporting failure raises, so a reset
    that did not take can never be reported as a successful start. A missing
    receipt returns false so the caller keeps waiting.
    """
    if reset == "none":
        return True
    kind = "reset_receipt" if reset == "baseline" else "relocation_receipt"
    journal = session_dir / "gateway.db"
    try:
        with sqlite3.connect(f"file:{journal.resolve()}?mode=ro", uri=True) as database:
            row = database.execute(
                "SELECT payload FROM events WHERE kind = ? ORDER BY seq DESC LIMIT 1",
                (kind,),
            ).fetchone()
    except sqlite3.Error:
        return False
    if row is None:
        return False
    try:
        receipt = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(receipt, dict) or receipt.get("ok") is not True:
        detail = ""
        if isinstance(receipt, dict):
            detail = str(receipt.get("error") or "")
        raise RuntimeSourceError(detail or f"{reset} reset did not verify")
    return True


def _control_state_running(session_dir: Path) -> bool:
    """Return whether the session's control state file reports ``running``."""
    control_state = session_dir / "control-state.json"
    try:
        state = json.loads(control_state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(state, dict) and state.get("state") == "running"


def _launch_failure_detail(capture: IO[bytes]) -> str:
    """Return the launcher's last stderr line as a bounded failure detail."""
    base = "launcher exited before creating a session"
    try:
        capture.seek(0)
        text = capture.read().decode(errors="replace").strip()
    except OSError:
        text = ""
    if text:
        last = text.splitlines()[-1].strip()
        if last:
            return f"{base}: {last}"
    return base


class CommandEffects(Protocol):
    """Effect boundary used by production and deterministic tests."""

    def validate(self, value: CommandSubmission) -> None:
        """Validate current authority and cursor without applying an effect."""

    def apply(self, command: Command) -> str | None:
        """Apply one previously persisted command."""

    def reconcile(self, command: Command) -> str | None:
        """Recover one interrupted command after backend restart."""


class RuntimeCommandEffects:
    """Apply commands through launcher and authenticated runtime boundaries."""

    def __init__(
        self,
        runtime_root: Path,
        runtime: RuntimeSource,
        *,
        cursor_resolver: Callable[[str, str], int] | None = None,
    ) -> None:
        self.runtime_root = runtime_root.expanduser().resolve()
        self.runtime = runtime
        self.cursor_resolver = cursor_resolver
        # Retain each launched process so its stdin pipe stays open. The agent
        # REPL exits on stdin EOF, so dropping the process would end the session.
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    def validate(self, value: CommandSubmission) -> None:
        if value.action == "start":
            if any(
                session.player_id == value.player_id and session.live
                for session in self.runtime.sessions()
            ):
                raise RuntimeSourceError(
                    "the selected player already has a live session"
                )
            return
        if value.session_id is None:
            raise RuntimeSourceError("session command requires a target session")
        session = self.runtime.session(value.session_id)
        if session is None:
            raise RuntimeSourceError("the selected session does not exist")
        if session.player_id != value.player_id:
            raise RuntimeSourceError("the selected session belongs to another player")
        if not session.live:
            raise RuntimeSourceError("the selected session is not live")
        # A stop targets the session itself, not a state snapshot: it needs
        # no cursor at all. Guide and revise instruct against observed state
        # and need the exact cursor.
        if value.action != "stop":
            if value.expected_cursor is None:
                raise RuntimeSourceError(
                    "session command requires an expected cursor"
                )
            if self.cursor_resolver is not None:
                self.cursor_resolver(value.session_id, value.expected_cursor)
            else:
                expected = _sequence(value.expected_cursor)
                if expected != session.latest_seq:
                    raise RuntimeSourceError(
                        "the selected session advanced, refresh before controlling it"
                    )
        if not value.force and not session.control_available:
            raise RuntimeSourceError(
                "the selected session has no available operator endpoint"
            )

    def apply(self, command: Command) -> str | None:
        if command.action == "start":
            return self._start(command)
        if command.session_id is None:
            raise RuntimeSourceError("session command requires a target session")
        session = self.runtime.session(command.session_id)
        if session is None:
            raise RuntimeSourceError("the selected session does not exist")
        if session.player_id != command.player_id:
            raise RuntimeSourceError("the selected session belongs to another player")
        expected = (
            session.latest_seq
            if command.action == "stop"
            else self._expected_sequence(command)
        )
        if command.action == "stop" and command.force:
            self._force_stop(command.session_id, command.player_id)
            self._release_process(command.session_id)
            return command.session_id
        self.runtime.control(
            command.session_id,
            request_id=command.id,
            action=command.action,
            instruction=command.instruction,
            expected_sequence=expected,
        )
        if command.action in {"guide", "revise"}:
            self._wake_process(command.session_id, command.id)
        if command.action == "stop":
            self._await_stop(command.session_id, command.player_id)
        return command.session_id

    def _wake_process(self, session_id: str, request_id: str) -> None:
        """Nudge an idle REPL to apply an accepted operator directive.

        Socket delivery reaches the operator mailbox, but an idle REPL only
        applies directives at an iteration boundary. Writing the wake envelope
        the agent recognises lets the directive apply without waiting for the
        next task. Only a process this effect owns can be woken;
        after a restart the socket delivery still applies on the next iteration.
        The agent recognises this envelope on stdin (`repl.py`), not as a task.
        """
        process = self._processes.get(session_id)
        if process is None or process.stdin is None or process.stdin.closed:
            return
        envelope = {"type": "operator_message", "request_id": request_id}
        try:
            process.stdin.write((json.dumps(envelope, sort_keys=True) + "\n").encode())
            process.stdin.flush()
        except OSError:
            pass

    def _await_stop(self, session_id: str, player_id: str) -> None:
        """Hold success until the accepted stop is a terminal fact.

        The agent gets a bounded grace period to leave on its own. Past it,
        only the verified owned process group is terminated, SIGTERM then
        SIGKILL, each with its own bounded wait. The registry records the
        outcome mode either way.
        """
        process = self._processes.get(session_id)
        if (
            process is not None
            and process.stdin is not None
            and not process.stdin.closed
        ):
            try:
                process.stdin.close()
            except OSError:
                pass
        mode = "cooperative"
        if not self._wait_for_exit(session_id, process, STOP_GRACE_SECONDS):
            mode = "forced_after_grace"
            process_id = self.runtime.process_id(session_id, player_id=player_id)
            try:
                process_group = os.getpgid(process_id)
            except ProcessLookupError:
                process_group = None
            if process_group is not None:
                if process_group != process_id:
                    raise RuntimeSourceError(
                        "the selected process group cannot be verified"
                    )
                os.killpg(process_group, signal.SIGTERM)
                if not self._wait_for_exit(
                    session_id, process, STOP_FORCE_SECONDS, pid=process_id
                ):
                    os.killpg(process_group, signal.SIGKILL)
                    if not self._wait_for_exit(
                        session_id, process, STOP_FORCE_SECONDS, pid=process_id
                    ):
                        raise RuntimeSourceError(
                            "the verified process group did not stop"
                        )
        self.runtime.record_stop(session_id, mode)
        self._release_process(session_id)

    def _wait_for_exit(
        self,
        session_id: str,
        process: subprocess.Popen[bytes] | None,
        budget: float,
        *,
        pid: int | None = None,
    ) -> bool:
        """True once the session process is gone, within the budget.

        An owned process handle is the direct truth. A resolved pid answers
        through a liveness probe. With neither, after a backend restart and
        before escalation, the registry state written by the exiting agent
        answers.
        """
        deadline = time.monotonic() + budget
        while True:
            if self._exited(session_id, process, pid):
                return True
            if time.monotonic() >= deadline:
                return self._exited(session_id, process, pid)
            time.sleep(0.25)

    def _exited(
        self,
        session_id: str,
        process: subprocess.Popen[bytes] | None,
        pid: int | None,
    ) -> bool:
        if process is not None:
            return process.poll() is not None
        if pid is not None:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            return False
        session = self.runtime.session(session_id)
        return session is None or not session.live

    def _release_process(self, session_id: str) -> None:
        """Close a stopped session's retained stdin and reap its process.

        The start effect keeps the launched process and its stdin pipe alive for
        the session lifetime. On stop the pipe is closed, the process is waited
        for, and the handle is dropped so nothing leaks past the session.
        """
        process = self._processes.pop(session_id, None)
        if process is None:
            return
        if process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def reconcile(self, command: Command) -> str | None:
        if command.action == "start":
            sessions = tuple(
                session
                for session in self.runtime.sessions()
                if session.player_id == command.player_id and session.live
            )
            if len(sessions) == 1:
                return sessions[0].id
            if sessions:
                raise RuntimeSourceError(
                    "interrupted start has ambiguous active sessions"
                )
        return self.apply(command)

    def _start(self, command: Command) -> str | None:
        records = self.runtime.player_records(command.player_id)
        if any(record.live for record in records):
            raise RuntimeSourceError("the selected player already has a live session")
        before = {record.session_id for record in records}
        agent_project = _agent_project()
        arguments = [
            "uv",
            "run",
            "--project",
            str(agent_project),
            "boukensha",
            "--no-tui",
            "--player-profile",
            command.player_id,
        ]
        standard_input: bytes | None = None
        if command.instruction:
            arguments.append("--initial-task-stdin")
            standard_input = (command.instruction + "\n").encode()
        if command.reset == "baseline":
            arguments.extend(("--reset-baseline", "level1-temple@1"))
        elif command.reset == "temple":
            arguments.append("--relocate-temple")
        environment = dict(os.environ)
        environment["BOUKENSHA_DIR"] = str(self.runtime_root)
        stderr_capture = tempfile.TemporaryFile()
        # stdin is always a pipe kept open: the agent REPL exits on EOF, so the
        # write end must live for the session's lifetime (see _processes).
        process = subprocess.Popen(
            arguments,
            cwd=str(agent_project.parents[1]),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=stderr_capture,
            start_new_session=True,
        )
        try:
            if process.stdin is None:
                raise RuntimeSourceError(
                    "the agent launcher did not expose its input channel"
                )
            if standard_input is not None:
                process.stdin.write(standard_input)
                process.stdin.flush()
            session_id = self._await_ready(process, command, before, stderr_capture)
        except BaseException:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            raise
        self._processes[session_id] = process
        return session_id

    def _await_ready(
        self,
        process: subprocess.Popen[bytes],
        command: Command,
        before: set[str],
        stderr_capture: IO[bytes],
    ) -> str:
        """Wait until the launched agent publishes a genuinely ready session.

        A session is ready only when it is new, running, its control state is
        ``running``, and any requested reset produced a successful receipt. A
        receipt reporting failure aborts the start.
        """
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeSourceError(_launch_failure_detail(stderr_capture))
            candidates = [
                record
                for record in self.runtime.player_records(command.player_id)
                if record.session_id not in before and record.state == "running"
            ]
            if candidates:
                # Newest first (created_at DESC), so the launched session leads.
                record = candidates[0]
                if _control_state_running(record.session_dir) and _reset_verified(
                    record.session_dir, command.reset
                ):
                    return record.session_id
            time.sleep(0.1)
        raise RuntimeSourceError("launcher did not publish a ready session in time")

    def _force_stop(self, session_id: str, player_id: str) -> None:
        process_id = self.runtime.process_id(session_id, player_id=player_id)
        try:
            process_group = os.getpgid(process_id)
        except ProcessLookupError as error:
            raise RuntimeSourceError(
                "the selected process is no longer running"
            ) from error
        if process_group != process_id:
            raise RuntimeSourceError("the selected process group cannot be verified")
        os.killpg(process_group, signal.SIGTERM)

    def _expected_sequence(self, command: Command) -> int:
        if command.expected_cursor is None or command.session_id is None:
            raise RuntimeSourceError("session command requires an expected cursor")
        if self.cursor_resolver is not None:
            return self.cursor_resolver(
                command.session_id,
                command.expected_cursor,
            )
        return _sequence(command.expected_cursor)


def _sequence(cursor: str | None) -> int:
    if cursor is None:
        raise RuntimeSourceError("session command requires an expected cursor")
    value = cursor.rsplit(":", 1)[-1]
    if not value.isdigit():
        raise RuntimeSourceError("expected cursor is invalid")
    return int(value)
