"""Deterministic retained-source fixtures for repository contract tests."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

REGISTRY_SCHEMA = """
CREATE TABLE sessions (
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
CREATE TABLE lifecycle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    at TEXT NOT NULL,
    state TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""

GATEWAY_SCHEMA = """
CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    session TEXT NOT NULL,
    at REAL NOT NULL,
    monotonic REAL NOT NULL,
    kind TEXT NOT NULL,
    trace_id TEXT,
    payload TEXT NOT NULL
);
CREATE INDEX events_by_session ON events(session, seq);
CREATE TABLE blobs (
    digest TEXT PRIMARY KEY,
    body BLOB NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class RetainedFixture:
    """Paths and identities for one deterministic retained session set."""

    config_dir: Path
    selected_session_id: str
    selected_gateway_session_id: str
    selected_session_dir: Path


def build_retained_fixture(root: Path, *, session_count: int = 66) -> RetainedFixture:
    """Build a versioned registry with one fully retained selected session."""
    config_dir = root / ".boukensha"
    config_dir.mkdir()
    source = config_dir / "registry.db"
    with sqlite3.connect(source) as database:
        database.executescript(REGISTRY_SCHEMA)
        database.execute("PRAGMA user_version=1")
        for index in range(session_count):
            session_id = f"session-{index:03d}"
            player_id = "alpha"
            session_dir = config_dir / "profiles" / player_id / "sessions" / session_id
            session_dir.mkdir(parents=True)
            manifest = session_dir / "session.json"
            manifest.write_text(
                json.dumps(
                    {
                        "layout_version": 1,
                        "player_id": player_id,
                        "session_id": session_id,
                        "operator_socket": str(root / "absent-operator.sock"),
                    }
                ),
                encoding="utf-8",
            )
            state = "running" if index == 0 else "stopped"
            gateway_session_id = f"gateway-{index:03d}"
            database.execute(
                """
                INSERT INTO sessions VALUES (
                    ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    session_id,
                    player_id,
                    "poucet",
                    f"agent-{index:03d}",
                    gateway_session_id,
                    str(session_dir),
                    str(manifest),
                    str(root / f"control-{index:03d}.sock"),
                    state,
                    1000 if state == "running" else None,
                    f"2026-08-01T00:{index:02d}:00+00:00",
                    f"2026-08-01T00:{index:02d}:01+00:00",
                    None if state == "running" else "2026-08-01T01:00:00+00:00",
                    None if state == "running" else 0,
                    None if state == "running" else "completed",
                    "complete",
                    0,
                ),
            )
            database.execute(
                """
                INSERT INTO lifecycle (session_id, at, state, detail)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    "2026-08-01T00:00:00+00:00",
                    state,
                    json.dumps({"reason": "fixture"}, sort_keys=True),
                ),
            )

    selected_dir = config_dir / "profiles" / "alpha" / "sessions" / "session-000"
    _write_selected_evidence(selected_dir)
    return RetainedFixture(
        config_dir=config_dir,
        selected_session_id="session-000",
        selected_gateway_session_id="gateway-000",
        selected_session_dir=selected_dir,
    )


def _write_selected_evidence(session_dir: Path) -> None:
    (session_dir / "agent.jsonl").write_text(
        '{"session_id":"session-000","player_id":"alpha",'
        '"phase":"prompt","text":"Find Fido"}\n'
        '{"session_id":"session-000","player_id":"alpha",'
        '"phase":"response","text":"I will look north"}\n',
        encoding="utf-8",
    )
    (session_dir / "operator-messages.json").write_text(
        json.dumps(
            {
                "version": 1,
                "messages": [
                    {
                        "request_id": "goal-1",
                        "action": "revise",
                        "instruction": "Find Fido",
                        "sent_at": "2026-08-01T00:00:00+00:00",
                        "applied_iteration": 1,
                        "applied_at": "2026-08-01T00:00:01+00:00",
                    },
                    {
                        "request_id": "nudge-1",
                        "action": "guide",
                        "instruction": "Check the park",
                        "sent_at": "2026-08-01T00:01:00+00:00",
                        "applied_iteration": 2,
                        "applied_at": "2026-08-01T00:01:01+00:00",
                    },
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(session_dir / "gateway.db") as database:
        database.executescript(GATEWAY_SCHEMA)
        database.execute("PRAGMA user_version=1")
        database.executemany(
            """
            INSERT INTO events (
                session, at, monotonic, kind, trace_id, payload
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "gateway-000",
                    1.0,
                    1.0,
                    "wire_in",
                    "trace-1",
                    '{"bytes":12}',
                ),
                (
                    "gateway-000",
                    2.0,
                    2.0,
                    "observation",
                    "trace-1",
                    '{"text":"A city street"}',
                ),
                (
                    "another-gateway",
                    3.0,
                    3.0,
                    "wire_in",
                    None,
                    '{"bytes":99}',
                ),
            ],
        )
