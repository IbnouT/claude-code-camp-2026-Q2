from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from pathlib import Path

import pytest

from observatory_v2_api.server import StartRequest, StartRequestError, Supervisor


def test_start_request_accepts_only_the_public_contract() -> None:
    assert StartRequest.decode(
        {"player_id": "poucet", "reset": "temple"}
    ) == StartRequest(player_id="poucet", reset="temple")

    with pytest.raises(StartRequestError) as unknown:
        StartRequest.decode(
            {"player_id": "poucet", "reset": "none", "instruction": "go"}
        )
    assert unknown.value.status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert unknown.value.code == "invalid_request"


@pytest.mark.parametrize("reset", ["none", "temple", "baseline"])
def test_start_request_supports_the_three_checkbox_results(reset: str) -> None:
    assert StartRequest.decode(
        {"player_id": "poucet", "reset": reset}
    ).reset == reset


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
