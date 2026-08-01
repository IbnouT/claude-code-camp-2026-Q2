from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from http import HTTPStatus
from pathlib import Path

import pytest

from observatory_v2_api.server import (
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


def test_idle_session_message_starts_first_turn_and_retains_history(
    tmp_path: Path,
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

    assert captured.read_text() == "Go to the warrior guild.\n"
    assert receipt["insertion"] == "first_turn"
    history = json.loads(
        (session_dir / "operator-messages.json").read_text()
    )
    assert history["messages"][0]["instruction"] == "Go to the warrior guild."
    assert history["messages"][0]["action"] == "revise"
    assert history["messages"][0]["applied_iteration"] == 1


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
