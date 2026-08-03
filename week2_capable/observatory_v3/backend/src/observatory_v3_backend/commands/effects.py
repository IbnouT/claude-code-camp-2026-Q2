"""Launcher and authenticated operator effects for durable commands."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ..sources.runtime import RuntimeSource, RuntimeSourceError
from .models import Command, CommandSubmission


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
        if value.expected_cursor is None:
            raise RuntimeSourceError("session command requires an expected cursor")
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
        expected = self._expected_sequence(command)
        if command.action == "stop" and command.force:
            self._force_stop(command.session_id, command.player_id)
            return command.session_id
        self.runtime.control(
            command.session_id,
            request_id=command.id,
            action=command.action,
            instruction=command.instruction,
            expected_sequence=expected,
        )
        return command.session_id

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
        if any(
            session.player_id == command.player_id and session.live
            for session in self.runtime.sessions()
        ):
            raise RuntimeSourceError("the selected player already has a live session")
        arguments = [
            sys.executable,
            "-m",
            "boukensha.launcher",
            "--no-tui",
            "--player-profile",
            command.player_id,
        ]
        standard_input: bytes | None = None
        if command.instruction:
            arguments.append("--task-stdin")
            standard_input = command.instruction.encode()
        environment = dict(os.environ)
        environment["BOUKENSHA_DIR"] = str(self.runtime_root)
        process = subprocess.Popen(
            arguments,
            env=environment,
            stdin=subprocess.PIPE if standard_input is not None else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if standard_input is not None and process.stdin is not None:
            process.stdin.write(standard_input)
            process.stdin.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            sessions = tuple(
                session
                for session in self.runtime.sessions()
                if session.player_id == command.player_id and session.live
            )
            if len(sessions) == 1:
                return sessions[0].id
            if process.poll() is not None:
                raise RuntimeSourceError("launcher exited before creating a session")
            time.sleep(0.05)
        raise RuntimeSourceError("launcher did not publish a session in time")

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
