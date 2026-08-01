"""Authenticated operator control at an agent iteration boundary."""

from __future__ import annotations

import json
import os
import secrets
import socket
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .message import Message
from .runtime import identity_environment

MAX_REQUEST_BYTES = 65_536
GUIDANCE_ACTIONS = frozenset({"guide", "revise"})
LIFECYCLE_ACTIONS = frozenset({"pause", "resume", "stop"})
ALL_ACTIONS = GUIDANCE_ACTIONS | LIFECYCLE_ACTIONS


class OperatorControlError(RuntimeError):
    """An operator request is invalid or cannot target this agent."""


class OperatorStopped(RuntimeError):
    """The authenticated operator stopped this agent."""


@dataclass(frozen=True)
class OperatorDirective:
    """One accepted directive waiting for an agent iteration boundary."""

    request_id: str
    action: str
    instruction: str | None
    accepted_state: str


class OperatorMessageJournal:
    """Durable sent-message history for the read-only Observatory."""

    def __init__(self, session_dir: Path) -> None:
        self.path = session_dir / "operator-messages.json"
        self.temporary = session_dir / ".operator-messages.tmp"
        self._lock = threading.Lock()

    def accept(self, request_id: str, action: str, instruction: str) -> None:
        with self._lock:
            value = self._read()
            messages = value["messages"]
            if any(message.get("request_id") == request_id for message in messages):
                return
            messages.append(
                {
                    "request_id": request_id,
                    "action": action,
                    "instruction": instruction,
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "applied_iteration": None,
                    "applied_at": None,
                }
            )
            self._write(value)

    def apply(self, request_id: str, iteration: int) -> None:
        with self._lock:
            value = self._read()
            for message in value["messages"]:
                if message.get("request_id") != request_id:
                    continue
                message["applied_iteration"] = iteration
                message["applied_at"] = datetime.now(timezone.utc).isoformat()
                self._write(value)
                return

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"version": 1, "messages": []}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise OperatorControlError(
                "operator message history is unreadable"
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("version") != 1
            or not isinstance(value.get("messages"), list)
        ):
            raise OperatorControlError("operator message history is invalid")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        self.temporary.write_text(
            json.dumps(value, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(self.temporary, 0o600)
        self.temporary.replace(self.path)


class OperatorMailbox:
    """Thread-safe control state consumed only by the agent loop."""

    def __init__(self, message_journal: OperatorMessageJournal | None = None) -> None:
        self._condition = threading.Condition()
        self._state = "running"
        self._pending: list[OperatorDirective] = []
        self._receipts: dict[str, dict[str, Any]] = {}
        self._message_journal = message_journal

    def attach_message_journal(self, journal: OperatorMessageJournal) -> None:
        """Attach the launcher session journal before serving requests."""
        with self._condition:
            self._message_journal = journal

    def submit(
        self,
        *,
        request_id: str,
        action: str,
        instruction: str | None,
    ) -> dict[str, Any]:
        with self._condition:
            if request_id in self._receipts:
                return self._receipts[request_id]
            if action not in ALL_ACTIONS:
                raise OperatorControlError(f"unsupported action {action!r}")
            clean = instruction.strip() if isinstance(instruction, str) else None
            if action in GUIDANCE_ACTIONS and not clean:
                raise OperatorControlError(
                    f"{action} requires a non-empty instruction"
                )
            if self._state == "stopped":
                raise OperatorControlError("the agent is already stopped")
            if action == "pause":
                self._state = "paused"
            elif action == "resume":
                self._state = "running"
            elif action == "stop":
                self._state = "stopped"
            if action in GUIDANCE_ACTIONS and self._message_journal is not None:
                self._message_journal.accept(request_id, action, clean or "")
            self._pending.append(
                OperatorDirective(request_id, action, clean, self._state)
            )
            receipt = {
                "ok": True,
                "request_id": request_id,
                "action": action,
                "state": self._state,
                "insertion": "next_iteration_boundary",
            }
            self._receipts[request_id] = receipt
            self._condition.notify_all()
            return receipt

    def checkpoint(self, context: Any, logger: Any, *, iteration: int) -> None:
        """Apply accepted directives before the next model request."""
        while True:
            with self._condition:
                pending = tuple(self._pending)
                self._pending.clear()
                state = self._state
            for directive in pending:
                logger.operator_control(
                    request_id=directive.request_id,
                    action=directive.action,
                    state=directive.accepted_state,
                    iteration=iteration,
                    instruction=directive.instruction,
                )
                if (
                    directive.action in GUIDANCE_ACTIONS
                    and self._message_journal is not None
                ):
                    self._message_journal.apply(directive.request_id, iteration)
                if directive.action == "guide":
                    context.add(
                        Message.user(
                            "Authenticated operator guidance for the active "
                            f"objective:\n{directive.instruction}"
                        )
                    )
                elif directive.action == "revise":
                    context.add(
                        Message.user(
                            "Authenticated operator objective revision. "
                            "Replace the active objective with this "
                            f"instruction:\n{directive.instruction}"
                        )
                    )
            if state == "stopped":
                raise OperatorStopped("agent stopped by authenticated operator")
            if state != "paused":
                return
            with self._condition:
                while self._state == "paused":
                    self._condition.wait()


class OperatorControlServer:
    """Small authenticated Unix-socket server for one runtime identity."""

    def __init__(
        self,
        socket_path: Path,
        token_path: Path,
        *,
        player_id: str,
        session_id: str,
        mailbox: OperatorMailbox,
    ) -> None:
        self.socket_path = socket_path
        self.token_path = token_path
        self.player_id = player_id
        self.session_id = session_id
        self.mailbox = mailbox
        self.mailbox.attach_message_journal(
            OperatorMessageJournal(self.token_path.parent)
        )
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._closing = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        if self.socket_path.exists():
            self.socket_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        server.listen(8)
        server.settimeout(0.2)
        self._socket = server
        self._thread = threading.Thread(
            target=self._serve,
            name=f"operator-control-{self.session_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._closing.set()
        server = self._socket
        if server is not None:
            server.close()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None
        self._socket = None
        self.socket_path.unlink(missing_ok=True)

    def _serve(self) -> None:
        while not self._closing.is_set():
            server = self._socket
            if server is None:
                return
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                response = self._handle(self._read(connection))
                try:
                    connection.sendall(
                        (json.dumps(response, sort_keys=True) + "\n").encode()
                    )
                except OSError:
                    continue

    def _handle(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            if request.get("protocol_version") != 1:
                raise OperatorControlError("unsupported protocol version")
            token = self.token_path.read_text(encoding="utf-8").strip()
            supplied = request.get("token")
            if not isinstance(supplied, str) or not secrets.compare_digest(
                supplied,
                token,
            ):
                raise OperatorControlError("operator authentication failed")
            if request.get("player_id") != self.player_id:
                raise OperatorControlError("operator player does not match")
            if request.get("session_id") != self.session_id:
                raise OperatorControlError("operator session does not match")
            request_id = request.get("request_id")
            action = request.get("action")
            if not isinstance(request_id, str) or not request_id:
                raise OperatorControlError("request_id is required")
            if not isinstance(action, str):
                raise OperatorControlError("action is required")
            receipt = self.mailbox.submit(
                request_id=request_id,
                action=action,
                instruction=request.get("instruction"),
            )
            self._write_state(receipt)
            return receipt
        except (OSError, OperatorControlError) as error:
            return {"ok": False, "error": str(error)}

    def _write_state(self, receipt: dict[str, Any]) -> None:
        """Project non-secret operator state for the read-only Observatory."""
        target = self.token_path.parent / "operator-state.json"
        temporary = self.token_path.parent / ".operator-state.tmp"
        value = {
            "version": 1,
            "state": receipt["state"],
            "request_id": receipt["request_id"],
            "action": receipt["action"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary.write_text(
            json.dumps(value, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(target)

    @staticmethod
    def _read(connection: socket.socket) -> dict[str, Any]:
        chunks: list[bytes] = []
        size = 0
        while size <= MAX_REQUEST_BYTES:
            part = connection.recv(min(4096, MAX_REQUEST_BYTES - size + 1))
            if not part:
                break
            chunks.append(part)
            size += len(part)
            if b"\n" in part:
                break
        if size > MAX_REQUEST_BYTES:
            return {}
        try:
            value = json.loads(b"".join(chunks).split(b"\n", 1)[0])
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return value if isinstance(value, dict) else {}


def start_operator_control(
    environment: dict[str, str] | None = None,
) -> tuple[OperatorMailbox, OperatorControlServer] | None:
    """Start control only inside a complete launcher-owned runtime."""
    identity = identity_environment(environment)
    session_dir = identity.get("session_dir")
    socket_value = identity.get("operator_socket")
    player_id = identity.get("player_id")
    session_id = identity.get("session_id")
    if not all((session_dir, socket_value, player_id, session_id)):
        return None
    mailbox = OperatorMailbox()
    server = OperatorControlServer(
        Path(str(socket_value)),
        Path(str(session_dir)) / "control.token",
        player_id=str(player_id),
        session_id=str(session_id),
        mailbox=mailbox,
    )
    server.start()
    return mailbox, server
