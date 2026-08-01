from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

from boukensha.context import Context
from boukensha.logger import Logger
from boukensha.operator_control import (
    OperatorControlError,
    OperatorControlServer,
    OperatorMailbox,
    OperatorStopped,
)


def request(
    path: Path,
    *,
    token: str,
    player: str = "alpha",
    session: str = "session-alpha",
    request_id: str = "request-1",
    action: str = "guide",
    instruction: str | None = "Look east",
) -> dict:
    payload = {
        "protocol_version": 1,
        "request_id": request_id,
        "action": action,
        "token": token,
        "player_id": player,
        "session_id": session,
        "instruction": instruction,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(path))
        client.sendall((json.dumps(payload) + "\n").encode())
        response = client.recv(65_536)
    return json.loads(response)


def server(tmp_path: Path):
    token = "test-token"
    token_path = tmp_path / "control.token"
    token_path.write_text(token, encoding="utf-8")
    mailbox = OperatorMailbox()
    digest = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]
    control = OperatorControlServer(
        Path(tempfile.gettempdir()) / f"boukensha-test-{digest}.sock",
        token_path,
        player_id="alpha",
        session_id="session-alpha",
        mailbox=mailbox,
    )
    control.start()
    return token, mailbox, control


def test_socket_authenticates_identity_and_is_idempotent(tmp_path: Path):
    token, mailbox, control = server(tmp_path)
    try:
        first = request(control.socket_path, token=token)
        repeated = request(control.socket_path, token=token)
        wrong_player = request(
            control.socket_path,
            token=token,
            player="beta",
            request_id="request-2",
        )
        wrong_token = request(
            control.socket_path,
            token="wrong",
            request_id="request-3",
        )
    finally:
        control.close()

    assert first["ok"] is True
    assert repeated == first
    state = json.loads(
        (tmp_path / "operator-state.json").read_text(encoding="utf-8")
    )
    assert state["state"] == "running"
    assert state["action"] == "guide"
    assert "instruction" not in state
    history = json.loads(
        (tmp_path / "operator-messages.json").read_text(encoding="utf-8")
    )
    assert len(history["messages"]) == 1
    assert history["messages"][0]["instruction"] == "Look east"
    assert history["messages"][0]["applied_iteration"] is None
    assert wrong_player == {
        "ok": False,
        "error": "operator player does not match",
    }
    assert wrong_token == {
        "ok": False,
        "error": "operator authentication failed",
    }
    with pytest.raises(OperatorControlError, match="non-empty"):
        mailbox.submit(
            request_id="missing-guidance",
            action="guide",
            instruction="",
        )


def test_guidance_enters_context_only_at_the_checkpoint(tmp_path: Path):
    token, mailbox, control = server(tmp_path)
    log = tmp_path / "agent.jsonl"
    logger = Logger(session_id="session-alpha", log=log)
    context = Context("system")
    try:
        response = request(control.socket_path, token=token)
        assert response["insertion"] == "next_iteration_boundary"
        assert context.messages == []

        mailbox.checkpoint(context, logger, iteration=3)
    finally:
        control.close()
        logger.close()

    assert len(context.messages) == 1
    assert "Authenticated operator guidance" in str(context.messages[0])
    assert "Look east" in context.messages[0].content[0].text
    records = [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
    ]
    applied = [
        record for record in records
        if record.get("phase") == "operator_control"
    ]
    assert applied[0]["request_id"] == "request-1"
    assert applied[0]["iteration"] == 3
    history = json.loads(
        (tmp_path / "operator-messages.json").read_text(encoding="utf-8")
    )
    assert history["messages"][0]["applied_iteration"] == 3
    assert history["messages"][0]["applied_at"] is not None


def test_pause_blocks_the_boundary_until_resume(tmp_path: Path):
    token, mailbox, control = server(tmp_path)
    logger = Logger(session_id="session-alpha", log=tmp_path / "agent.jsonl")
    context = Context("system")
    completed = threading.Event()

    def checkpoint() -> None:
        mailbox.checkpoint(context, logger, iteration=4)
        completed.set()

    try:
        request(
            control.socket_path,
            token=token,
            action="pause",
            instruction=None,
        )
        assert json.loads(
            (tmp_path / "operator-state.json").read_text(encoding="utf-8")
        )["state"] == "paused"
        worker = threading.Thread(target=checkpoint)
        worker.start()
        time.sleep(0.05)
        assert completed.is_set() is False
        records = [
            json.loads(line)
            for line in (tmp_path / "agent.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        assert any(
            record.get("phase") == "operator_control"
            and record.get("action") == "pause"
            and record.get("state") == "paused"
            for record in records
        )

        request(
            control.socket_path,
            token=token,
            request_id="request-2",
            action="resume",
            instruction=None,
        )
        assert json.loads(
            (tmp_path / "operator-state.json").read_text(encoding="utf-8")
        )["state"] == "running"
        worker.join(timeout=1)
        assert completed.is_set() is True
    finally:
        control.close()
        logger.close()


def test_stop_raises_at_the_next_boundary(tmp_path: Path):
    token, mailbox, control = server(tmp_path)
    logger = Logger(session_id="session-alpha", log=tmp_path / "agent.jsonl")
    try:
        request(
            control.socket_path,
            token=token,
            action="stop",
            instruction=None,
        )
        with pytest.raises(OperatorStopped):
            mailbox.checkpoint(Context("system"), logger, iteration=5)
    finally:
        control.close()
        logger.close()
