from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from pathlib import Path

import pytest

from backend.launcher.server import (
    MessageRequest,
    MessageRequestError,
    StartRequest,
    StartRequestError,
    Supervisor,
)


def test_start_request_accepts_only_the_public_contract() -> None:
    assert StartRequest.decode(
        {
            "player_id": "poucet",
            "reset": "temple",
            "objective": "Find the bakery.",
        }
    ) == StartRequest(
        player_id="poucet",
        reset="temple",
        objective="Find the bakery.",
    )

    with pytest.raises(StartRequestError) as unknown:
        StartRequest.decode(
            {
                "player_id": "poucet",
                "reset": "none",
                "objective": "Find the bakery.",
                "instruction": "go",
            }
        )
    assert unknown.value.status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert unknown.value.code == "invalid_request"


@pytest.mark.parametrize("reset", ["none", "temple", "baseline"])
def test_start_request_supports_the_three_checkbox_results(reset: str) -> None:
    assert StartRequest.decode(
        {
            "player_id": "poucet",
            "reset": reset,
            "objective": "Find the bakery.",
        }
    ).reset == reset


def test_start_request_requires_a_bounded_initial_goal() -> None:
    assert StartRequest.decode(
        {"player_id": "poucet", "reset": "none"}
    ).objective is None
    assert StartRequest.decode(
        {"player_id": "poucet", "reset": "none", "objective": "  "}
    ).objective is None

    with pytest.raises(StartRequestError) as wrong_type:
        StartRequest.decode(
            {"player_id": "poucet", "reset": "none", "objective": 42}
        )
    assert wrong_type.value.code == "invalid_objective"

    with pytest.raises(StartRequestError) as too_long:
        StartRequest.decode(
            {
                "player_id": "poucet",
                "reset": "none",
                "objective": "x" * 4_001,
            }
        )
    assert too_long.value.code == "invalid_objective"


def test_message_request_requires_one_bounded_instruction() -> None:
    assert MessageRequest.decode(
        {
            "request_id": "message-1",
            "action": "revise",
            "instruction": "  Go to the warrior guild.  ",
        }
    ) == MessageRequest(
        request_id="message-1",
        action="revise",
        instruction="Go to the warrior guild.",
    )

    with pytest.raises(MessageRequestError) as missing:
        MessageRequest.decode(
            {
                "request_id": "message-1",
                "action": "guide",
                "instruction": "  ",
            }
        )
    assert missing.value.code == "invalid_instruction"


def test_start_with_goal_uses_persistent_stdin_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = type(
        "Process",
        (),
        {
            "stdin": io.BytesIO(),
            "stderr": io.BytesIO(),
            "poll": lambda self: None,
        },
    )()
    captured: dict[str, object] = {}

    def popen(command: list[str], **kwargs: object) -> object:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return process

    supervisor = Supervisor(tmp_path, tmp_path / "config", idle_timeout_seconds=0)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(supervisor, "_session_ids", lambda player_id: [])
    monkeypatch.setattr(
        supervisor,
        "_wait_for_ready",
        lambda process, **kwargs: "session-123",
    )
    monkeypatch.setattr(supervisor, "_start_idle_watch", lambda session_id: None)

    session_id = supervisor.start(
        StartRequest(
            player_id="poucet",
            reset="none",
            objective="Find the bakery.",
        )
    )

    assert session_id == "session-123"
    command = captured["command"]
    assert isinstance(command, list)
    assert "--initial-task-stdin" in command
    assert "--task-stdin" not in command
    assert process.stdin.getvalue() == b"Find the bakery.\n"
    assert process.stdin.closed is False


def test_idle_session_message_starts_first_turn_and_retains_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    session_id = "42085051-7b6e-4214-b610-308a1db4c4df"
    session_dir = (
        config_root / "profiles" / "poucet" / "sessions" / session_id
    )
    session_dir.mkdir(parents=True)
    registry = config_root / "registry.db"
    with sqlite3.connect(registry) as database:
        database.execute(
            "CREATE TABLE sessions ("
            "session_id TEXT, player_id TEXT, state TEXT, session_dir TEXT, "
            "created_at TEXT, updated_at TEXT, ended_at TEXT)"
        )
        database.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                "poucet",
                "running",
                str(session_dir),
                "2026-08-01T00:00:00Z",
                "2026-08-01T00:00:00Z",
                None,
            ),
        )
    captured = tmp_path / "instruction.txt"
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,sys;"
                f"pathlib.Path({str(captured)!r}).write_text(sys.stdin.readline())"
            ),
        ],
        stdin=subprocess.PIPE,
    )
    supervisor = Supervisor(tmp_path, config_root)
    supervisor.processes[session_id] = process
    monkeypatch.setattr(
        supervisor,
        "_request_operator_message",
        lambda row, *, request: {
            "request_id": request.request_id,
            "action": request.action,
            "state": "running",
            "insertion": "next_iteration_or_turn",
        },
    )

    receipt = supervisor.message(
        session_id,
        MessageRequest(
            request_id="message-1",
            action="revise",
            instruction="Go to the warrior guild.",
        ),
    )
    assert process.stdin is not None
    process.stdin.close()
    assert process.wait(timeout=5) == 0

    assert json.loads(captured.read_text()) == {
        "request_id": "message-1",
        "type": "operator_message",
    }
    assert receipt["insertion"] == "next_iteration_or_turn"


def test_message_uses_the_verified_operator_identity(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    session_id = "42085051-7b6e-4214-b610-308a1db4c4df"
    session_dir = (
        config_root / "profiles" / "poucet" / "sessions" / session_id
    )
    session_dir.mkdir(parents=True)
    digest = hashlib.sha256(session_id.encode()).hexdigest()[:20]
    socket_path = (
        Path(tempfile.gettempdir()) / f"boukensha-{digest}-operator.sock"
    )
    token = "operator-token"
    (session_dir / "control.token").write_text(token, encoding="utf-8")
    (session_dir / "session.json").write_text(
        json.dumps({
            "session_id": session_id,
            "player_id": "poucet",
            "operator_socket": str(socket_path),
        }),
        encoding="utf-8",
    )
    with sqlite3.connect(session_dir / "gateway.db") as database:
        database.execute("CREATE TABLE events (seq INTEGER)")
        database.execute("INSERT INTO events VALUES (42)")
    received: dict[str, object] = {}
    ready = threading.Event()

    def serve() -> None:
        socket_path.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(socket_path))
            server.listen(1)
            ready.set()
            connection, _ = server.accept()
            with connection:
                received.update(json.loads(connection.recv(65_536)))
                connection.sendall(json.dumps({
                    "ok": True,
                    "request_id": "message-1",
                    "action": "revise",
                    "state": "running",
                }).encode())

    worker = threading.Thread(target=serve)
    worker.start()
    ready.wait(timeout=1)
    supervisor = Supervisor(tmp_path, config_root)
    try:
        receipt = supervisor._request_operator_message(
            {
                "session_id": session_id,
                "player_id": "poucet",
                "session_dir": str(session_dir),
            },
            request=MessageRequest(
                request_id="message-1",
                action="revise",
                instruction="Find a peacekeeper.",
            ),
        )
    finally:
        worker.join(timeout=1)
        socket_path.unlink(missing_ok=True)

    assert received["token"] == token
    assert received["expected_sequence"] == 42
    assert received["instruction"] == "Find a peacekeeper."
    assert receipt["insertion"] == "next_iteration_or_turn"


def test_ready_waits_for_the_requested_receipt(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "control-state.json").write_text(
        json.dumps({"state": "running"}),
        encoding="utf-8",
    )
    with sqlite3.connect(session_dir / "gateway.db") as database:
        database.execute(
            "CREATE TABLE events (seq INTEGER, kind TEXT, payload TEXT)"
        )
        database.execute(
            "INSERT INTO events VALUES (?, ?, ?)",
            (1, "relocation_receipt", json.dumps({"ok": True})),
        )

    assert Supervisor._ready(session_dir, "none") is True
    assert Supervisor._ready(session_dir, "temple") is True
    assert Supervisor._ready(session_dir, "baseline") is False


def test_idle_timeout_is_configurable_and_zero_disables_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOUKENSHA_OBSERVATORY_IDLE_TIMEOUT_SECONDS", raising=False)
    assert Supervisor(tmp_path, tmp_path).idle_timeout_seconds == 1_800

    monkeypatch.setenv("BOUKENSHA_OBSERVATORY_IDLE_TIMEOUT_SECONDS", "45")
    assert Supervisor(tmp_path, tmp_path).idle_timeout_seconds == 45

    monkeypatch.setenv("BOUKENSHA_OBSERVATORY_IDLE_TIMEOUT_SECONDS", "0")
    assert Supervisor(tmp_path, tmp_path).idle_timeout_seconds == 0

    monkeypatch.setenv("BOUKENSHA_OBSERVATORY_IDLE_TIMEOUT_SECONDS", "later")
    with pytest.raises(ValueError, match="non-negative number"):
        Supervisor(tmp_path, tmp_path)


def test_idle_timeout_uses_retained_or_operator_activity(tmp_path: Path) -> None:
    log = tmp_path / "agent.jsonl"
    supervisor = Supervisor(
        tmp_path,
        tmp_path,
        idle_timeout_seconds=30,
    )
    old = time.time() - 31

    log.write_text(
        json.dumps({"phase": "turn_end", "reason": "completed"}) + "\n"
    )
    os.utime(log, (old, old))
    assert supervisor._idle_expired(tmp_path, operator_at=0) is True

    log.write_text(json.dumps({"phase": "prompt"}) + "\n")
    now = time.time()
    os.utime(log, (now, now))
    assert supervisor._idle_expired(tmp_path, operator_at=0) is False

    os.utime(log, (old, old))
    assert supervisor._idle_expired(tmp_path, operator_at=0) is True

    log.write_text(json.dumps({"phase": "session_start"}) + "\n")
    os.utime(log, (old, old))
    assert supervisor._idle_expired(
        tmp_path,
        operator_at=time.time(),
    ) is False


def test_idle_watcher_uses_the_supervised_idle_stop_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped = threading.Event()
    received: dict[str, str] = {}
    process = type("Process", (), {"poll": lambda self: None})()
    supervisor = Supervisor(
        tmp_path,
        tmp_path,
        idle_timeout_seconds=0.01,
        idle_poll_seconds=0.01,
    )
    supervisor.processes["session-123"] = process
    monkeypatch.setattr(
        supervisor,
        "_session",
        lambda session_id: {"state": "running"},
    )
    monkeypatch.setattr(
        supervisor,
        "_safe_session_dir",
        lambda row: tmp_path,
    )
    monkeypatch.setattr(
        supervisor,
        "_idle_expired",
        lambda session_dir, operator_at: True,
    )

    def stop(session_id: str, *, reason: str) -> None:
        received.update(session_id=session_id, reason=reason)
        stopped.set()

    monkeypatch.setattr(supervisor, "stop", stop)
    supervisor._watch_idle("session-123")

    assert stopped.is_set()
    assert received == {
        "session_id": "session-123",
        "reason": "idle_timeout",
    }
