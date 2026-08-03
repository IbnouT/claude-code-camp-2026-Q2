"""Deterministic retained fixture for the B9 readiness gate."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ..fixtures import RetainedFixture, build_retained_fixture


@dataclass(frozen=True, slots=True)
class ReadinessFixture:
    """One sanitized fixture and its stable provenance."""

    retained: RetainedFixture
    digest: str
    sessions: int
    agent_records: int
    gateway_events: int
    running_sessions: int
    stopped_sessions: int
    registry_schema: int
    gateway_schema: int


def build_readiness_fixture(root: Path) -> ReadinessFixture:
    """Build all retained source shapes required by the B9 system gate."""
    root.mkdir(parents=True, exist_ok=True)
    retained = build_retained_fixture(root, session_count=38)
    identity = {
        "session_id": retained.selected_session_id,
        "player_id": "alpha",
    }
    records = [
        {
            **identity,
            "phase": "session_start",
            "objective": {"title": "Representative load"},
            "at": "2026-08-01T00:00:00+00:00",
        },
        *(
            {
                **identity,
                "phase": "reasoning",
                "text": f"evidence-{index:04d} " + "x" * 220,
                "at": f"2026-08-01T00:00:{index % 60:02d}+00:00",
            }
            for index in range(1, 5_000)
        ),
    ]
    (retained.selected_session_dir / "agent.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    with sqlite3.connect(retained.selected_session_dir / "gateway.db") as database:
        database.execute("DELETE FROM events")
        database.executemany(
            """
            INSERT INTO events (
                session, at, monotonic, kind, trace_id, payload
            ) VALUES (?, ?, ?, 'observation', NULL, ?)
            """,
            (
                (
                    retained.selected_gateway_session_id,
                    float(sequence),
                    float(sequence),
                    json.dumps(
                        {
                            "direction": "north",
                            "place_id": f"place:{sequence % 250}",
                            "title": f"Place {sequence % 250}",
                        },
                        sort_keys=True,
                    ),
                )
                for sequence in range(1, 2_001)
            ),
        )
    partial_dir = (
        retained.config_dir / "profiles" / "alpha" / "sessions" / "session-037"
    )
    (partial_dir / "agent.jsonl").write_bytes(
        b'{"session_id":"session-037","player_id":"alpha","phase":"prompt"}\n'
        b'{"session_id":"session-037"'
    )
    with sqlite3.connect(retained.config_dir / "registry.db") as database:
        database.execute(
            """
            UPDATE sessions
            SET experiment_id = 'readiness-experiment',
                run_id = 'readiness-sample'
            WHERE session_id = 'session-002'
            """
        )
        database.execute(
            """
            INSERT INTO lifecycle (session_id, at, state, detail)
            VALUES (
                'session-003',
                '2026-08-01T00:00:02+00:00',
                'stopped',
                '{"reason":"interrupted_start"}'
            )
            """
        )
        registry_schema = int(database.execute("PRAGMA user_version").fetchone()[0])
        states = database.execute(
            "SELECT state, COUNT(*) FROM sessions GROUP BY state"
        ).fetchall()
    with sqlite3.connect(
        retained.selected_session_dir / "gateway.db"
    ) as gateway_database:
        gateway_schema = int(
            gateway_database.execute("PRAGMA user_version").fetchone()[0]
        )
    state_counts = {str(state): int(count) for state, count in states}
    return ReadinessFixture(
        retained=retained,
        digest=_fixture_digest(retained),
        sessions=38,
        agent_records=5_000,
        gateway_events=2_000,
        running_sessions=state_counts.get("running", 0),
        stopped_sessions=state_counts.get("stopped", 0),
        registry_schema=registry_schema,
        gateway_schema=gateway_schema,
    )


def _fixture_digest(retained: RetainedFixture) -> str:
    with sqlite3.connect(retained.config_dir / "registry.db") as database:
        registry_rows = database.execute(
            """
            SELECT session_id, player_id, character, agent_id,
                   gateway_session_id, experiment_id, run_id, state,
                   created_at, updated_at, ended_at, exit_code, stop_mode,
                   capture_status, legacy
            FROM sessions
            ORDER BY session_id
            """
        ).fetchall()
        lifecycle_rows = database.execute(
            """
            SELECT session_id, at, state, detail
            FROM lifecycle
            ORDER BY session_id, id
            """
        ).fetchall()
    with sqlite3.connect(
        retained.selected_session_dir / "gateway.db"
    ) as gateway_database:
        gateway_rows = gateway_database.execute(
            """
            SELECT seq, session, at, monotonic, kind, trace_id, payload
            FROM events
            ORDER BY seq
            """
        ).fetchall()
    canonical = {
        "agent_sha256": sha256(
            (retained.selected_session_dir / "agent.jsonl").read_bytes()
        ).hexdigest(),
        "gateway_rows": gateway_rows,
        "lifecycle_rows": lifecycle_rows,
        "operator_sha256": sha256(
            (retained.selected_session_dir / "operator-messages.json").read_bytes()
        ).hexdigest(),
        "partial_sha256": sha256(
            (
                retained.config_dir
                / "profiles"
                / "alpha"
                / "sessions"
                / "session-037"
                / "agent.jsonl"
            ).read_bytes()
        ).hexdigest(),
        "registry_rows": registry_rows,
    }
    return sha256(
        json.dumps(
            canonical,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
