from __future__ import annotations

import asyncio
import hashlib
import os
import json
import socket
import sqlite3
import tempfile
import threading
from pathlib import Path

import httpx
from mud_gateway.journal import Journal

from backend.app import create_app
from backend.contracts import LiveMilestone, LiveTimelineItem
from backend.projections.live import _objective, _quiet_cohorts
from backend.settings import Settings
from backend.sources.runtime import RuntimeSource, RuntimeSourceError


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
    capture_status TEXT NOT NULL DEFAULT 'complete',
    legacy INTEGER NOT NULL DEFAULT 0
);
"""


def test_compatibility_objective_ignores_operator_guidance():
    events = [
        {
            "phase": "prompt",
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": "Find the warrior guild",
                }],
            }],
        },
        {
            "phase": "prompt",
            "messages": [
                {
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": "Find the warrior guild",
                    }],
                },
                {
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": (
                            "Authenticated operator guidance for the active "
                            "objective:\nTry the western exit"
                        ),
                    }],
                },
            ],
        },
    ]

    assert _objective(events) == "Find the warrior guild"


def test_quiet_cohorts_follow_contiguous_activity_runs_between_landmarks():
    def item(
        sequence: int,
        source: str,
        kind: str,
    ) -> LiveTimelineItem:
        return LiveTimelineItem(
            id=f"{source}-{sequence}-{kind}",
            sequence=sequence,
            at=float(sequence),
            source=source,
            kind=kind,
            label=kind,
        )

    timeline = (
        item(1, "gateway", "observation"),
        item(2, "gateway", "observation"),
        item(3, "agent", "iteration"),
        item(4, "gateway", "position"),
        item(5, "agent", "iteration"),
        item(6, "gateway", "observation"),
        item(6, "agent", "response"),
        item(7, "agent", "iteration"),
        item(8, "gateway", "combat"),
        item(9, "gateway", "combat"),
        item(10, "gateway", "combat"),
        item(11, "agent", "operator_control"),
        item(12, "agent", "iteration"),
    )
    milestones = (
        LiveMilestone(
            kind="level_up",
            sequence=6,
            at=6,
            previous=3,
            current=4,
            evidence="gateway observation seq 6",
        ),
    )

    tagged = _quiet_cohorts(timeline, milestones)

    assert [entry.quiet_cohort for entry in tagged] == [
        "quiet-1",
        "quiet-1",
        "quiet-2",
        None,
        "quiet-3",
        None,
        None,
        "quiet-4",
        None,
        "quiet-5",
        None,
        None,
        "quiet-6",
    ]


def add_session(
    root: Path,
    *,
    player: str,
    character: str,
    session: str,
    gateway_session: str,
    state: str,
    cost: float,
    pid: int | None = None,
) -> Path:
    session_dir = root / "profiles" / player / "sessions" / session
    session_dir.mkdir(parents=True)
    digest = hashlib.sha256(session.encode()).hexdigest()[:20]
    operator_socket = (
        Path(tempfile.gettempdir()) / f"boukensha-{digest}-operator.sock"
    )
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "player_id": player,
                "session_id": session,
                "gateway_session_id": gateway_session,
                "operator_socket": str(operator_socket),
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "control.token").write_text(
        f"token-{player}",
        encoding="utf-8",
    )
    journal = Journal(session_dir / "gateway.db")
    journal.append(
        gateway_session,
        "session_open",
        {"character": character},
        at=1,
        monotonic=1,
    )
    journal.append(
        gateway_session,
        "model_response",
        {"cost_usd": cost, "output_tokens": int(cost * 1_000)},
        at=2,
        monotonic=2,
    )
    journal.close()
    identity = {
        "player_id": player,
        "agent_id": f"agent-{player}",
        "session_id": session,
        "gateway_session_id": gateway_session,
    }
    (session_dir / "agent.jsonl").write_text(
        "\n".join(
            json.dumps(record, separators=(",", ":"))
            for record in (
                {
                    "phase": "session_start",
                    "model": "test-model",
                    "provider": "test-provider",
                    "system": "Observe every retained interaction.",
                    "max_iterations": 25,
                    "max_output_tokens": 1_024,
                    "context_window": 200_000,
                    "objective": {
                        "title": f"Explore as {character}",
                        "clue": None,
                        "source_kind": "operator",
                        "revision": 1,
                    },
                    "at": "1970-01-01T00:00:00.500+00:00",
                    **identity,
                },
                {
                    "phase": "prompt",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Explore as {character}",
                                }
                            ],
                        }
                    ],
                    "at": "1970-01-01T00:00:01+00:00",
                    **identity,
                },
                {
                    "phase": "model_request",
                    "model": "test-model",
                    "provider": "test-provider",
                    "request": {
                        "model": "test-model",
                        "messages": [{
                            "role": "user",
                            "content": f"Explore as {character}",
                        }],
                        "api_key": "must-not-cross-read-boundary",
                    },
                    "at": "1970-01-01T00:00:01.250+00:00",
                    **identity,
                },
                {
                    "phase": "provider_response",
                    "model": "test-model",
                    "provider": "test-provider",
                    "response": {
                        "content": [{
                            "type": "text",
                            "text": f"I will explore as {character}.",
                        }],
                    },
                    "at": "1970-01-01T00:00:01.375+00:00",
                    **identity,
                },
                {
                    "phase": "response",
                    "model": "test-model",
                    "text": f"I will explore as {character}.",
                    "content": [{
                        "type": "text",
                        "text": f"I will explore as {character}.",
                    }],
                    "cost_usd": cost,
                    "usage": {
                        "input_tokens": int(cost * 1_000),
                        "output_tokens": 7,
                    },
                    "at": "1970-01-01T00:00:01.500+00:00",
                    **identity,
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    database = sqlite3.connect(root / "registry.db")
    database.execute(
        """
        INSERT INTO sessions (
            session_id, player_id, character, agent_id,
            gateway_session_id, experiment_id, run_id, session_dir,
            manifest_path, control_socket, state, pid, created_at,
            updated_at, ended_at, exit_code, capture_status, legacy
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0)
        """,
        (
            session,
            player,
            character,
            f"agent-{player}",
            gateway_session,
            str(session_dir),
            str(session_dir / "session.json"),
            str(root / f"{session}.sock"),
            state,
            # A row claiming to run is only believed while its process is
            # there, so a session meant to read as live carries a real one.
            (os.getpid() if pid is None else pid)
            if state in {"starting", "running", "draining", "quarantined"}
            else None,
            f"2026-07-30T00:00:0{1 if player == 'alpha' else 2}Z",
            "2026-07-30T00:01:00Z",
            None if state == "running" else "2026-07-30T00:02:00Z",
            "complete",
        ),
    )
    database.commit()
    database.close()
    return session_dir


def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".boukensha"
    root.mkdir()
    database = sqlite3.connect(root / "registry.db")
    database.executescript(REGISTRY_SCHEMA)
    database.close()
    add_session(
        root,
        player="alpha",
        character="Alpha",
        session="session-alpha",
        gateway_session="gateway-alpha",
        state="running",
        cost=0.11,
    )
    add_session(
        root,
        player="beta",
        character="Beta",
        session="session-beta",
        gateway_session="gateway-beta",
        state="stopped",
        cost=0.22,
    )
    return root


async def test_catalog_discovers_all_players_and_session_states(tmp_path: Path):
    root = runtime_root(tmp_path)
    alpha_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    (alpha_dir / "operator-state.json").write_text(
        json.dumps({"state": "paused"}),
        encoding="utf-8",
    )
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/sessions")
        capabilities = await client.get("/api/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert [player["id"] for player in payload["players"]] == ["alpha", "beta"]
    assert [session["id"] for session in payload["sessions"]] == [
        "session-alpha",
        "session-beta",
    ]
    assert payload["sessions"][0]["live"] is True
    assert payload["sessions"][0]["control_state"] == "paused"
    assert payload["sessions"][0]["event_count"] == 2
    assert payload["sessions"][0]["objective"] == "Explore as Alpha"
    assert payload["sessions"][0]["goal_count"] == 1
    assert payload["sessions"][0]["nudge_count"] == 0
    assert payload["sessions"][1]["live"] is False
    sources = {
        source["id"]: source
        for source in capabilities.json()["sources"]
    }
    assert sources["agent"]["state"] == "ready"


async def test_runtime_session_investigation_opens_any_launcher_run(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get(
            "/api/sessions/session-beta/investigation"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_kind"] == "runtime_session"
    assert payload["run"]["lifecycle"] == "stopped"
    assert payload["run"]["capture_status"] == "complete"
    assert payload["run"]["cost_usd"] == 0.22
    assert payload["player_id"] == "beta"
    assert payload["objective"] == "Explore as Beta"
    assert payload["cost"]["total_usd"] == 0.22
    assert payload["cost"]["fresh_input_tokens"] == 220
    assert {
        (record["source"], record["kind"])
        for record in payload["records"]
    } >= {
        ("agent", "session_start"),
        ("agent", "model_request"),
        ("agent", "response"),
        ("gateway", "session_open"),
        ("gateway", "model_response"),
    }


async def test_objective_revisions_and_nudges_remain_distinct_everywhere(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    (session_dir / "operator-messages.json").write_text(
        json.dumps(
            {
                "version": 1,
                "messages": [
                    {
                        "request_id": "goal-1",
                        "action": "revise",
                        "instruction": "Find the temple",
                        "sent_at": "1970-01-01T00:00:00.600+00:00",
                        "applied_iteration": 0,
                        "applied_at": "1970-01-01T00:00:00.700+00:00",
                    },
                    {
                        "request_id": "goal-2",
                        "action": "revise",
                        "instruction": "Practice at the warrior guild",
                        "sent_at": "1970-01-01T00:00:02.600+00:00",
                        "applied_iteration": 1,
                        "applied_at": "1970-01-01T00:00:02.700+00:00",
                    },
                    {
                        "request_id": "guide-1",
                        "action": "guide",
                        "instruction": "Return through the western gate",
                        "sent_at": "1970-01-01T00:00:02.800+00:00",
                        "applied_iteration": 1,
                        "applied_at": "1970-01-01T00:00:02.900+00:00",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        catalog = (await client.get("/api/sessions")).json()
        investigation = (
            await client.get("/api/sessions/session-alpha/investigation")
        ).json()

    session = catalog["sessions"][0]
    assert session["objective"] == "Practice at the warrior guild"
    assert session["goal_count"] == 3
    assert session["nudge_count"] == 1
    assert investigation["objective"] == "Practice at the warrior guild"
    assert investigation["run"]["goal_epochs"] == 3
    controls = {
        record["kind"]: record
        for record in investigation["records"]
        if record["kind"] in {"goal_revision", "guidance"}
    }
    assert controls["goal_revision"]["fields"]["action"] == "revise"
    assert controls["guidance"]["fields"]["action"] == "guide"
    assert controls["guidance"]["preview"] == (
        "Return through the western gate"
    )


async def test_runtime_investigation_exposes_complete_model_exchange(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    agent_log = (
        root
        / "profiles"
        / "beta"
        / "sessions"
        / "session-beta"
        / "agent.jsonl"
    )
    identity = {
        "player_id": "beta",
        "agent_id": "agent-beta",
        "session_id": "session-beta",
        "gateway_session_id": "gateway-beta",
    }
    with agent_log.open("a", encoding="utf-8") as handle:
        for event in (
            {
                "phase": "tool_call",
                "id": "tool-use-1",
                "name": "tbamud__look",
                "input": {},
                "at": "1970-01-01T00:00:01.625+00:00",
                **identity,
            },
            {
                "phase": "tool_result",
                "tool_use_id": "tool-use-1",
                "name": "tbamud__look",
                "result": "The Pet Shop",
                "ok": True,
                "error": False,
                "stages": {
                    "mcp_result": json.dumps({
                        "trace_id": "trace-look-1",
                        "text": "The Pet Shop",
                    }),
                    "result_mode": "minimal",
                    "rendered_result": "The Pet Shop",
                    "truncated_chars": 0,
                    "model_input": "The Pet Shop",
                    "error": False,
                },
                "at": "1970-01-01T00:00:01.750+00:00",
                **identity,
            },
        ):
            handle.write(json.dumps(event) + "\n")
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        payload = (
            await client.get("/api/sessions/session-beta/investigation")
        ).json()

    by_kind = {
        record["kind"]: record
        for record in payload["records"]
        if record["source"] == "agent"
    }
    assert by_kind["session_start"]["fields"]["system"] == (
        "Observe every retained interaction."
    )
    assert by_kind["model_request"]["fields"]["request"]["messages"][0] == {
        "role": "user",
        "content": "Explore as Beta",
    }
    assert by_kind["model_request"]["fields"]["request"]["api_key"] == "[REDACTED]"
    assert by_kind["response"]["fields"]["content"][0]["text"] == (
        "I will explore as Beta."
    )
    assert by_kind["provider_response"]["fields"]["response"]["content"][0][
        "text"
    ] == "I will explore as Beta."
    stages = by_kind["tool_result"]["fields"]["stages"]
    assert json.loads(stages["mcp_result"])["trace_id"] == "trace-look-1"
    assert stages["result_mode"] == "minimal"
    assert stages["rendered_result"] == "The Pet Shop"
    assert stages["model_input"] == "The Pet Shop"


async def test_wire_evidence_drills_to_integrity_checked_bytes(tmp_path: Path):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "beta" / "sessions" / "session-beta"
    )
    journal = Journal(session_dir / "gateway.db")
    body = b"\x1b[32mAvailable pets are:\x1b[0m\r\n  300 - the puppy\r\n"
    digest = journal.put_blob(body)
    wire = journal.append(
        "gateway-beta",
        "wire",
        {
            "direction": "in",
            "bytes": len(body),
            "redacted": False,
            "digest": digest,
        },
        trace_id="trace-pets",
        at=3,
        monotonic=3,
    )
    journal.append(
        "gateway-beta",
        "wire_text",
        {
            "direction": "in",
            "wire_seq": wire.seq,
            "bytes": len(body),
            "redacted": False,
            "encoding": "latin-1",
            "ansi": "preserved",
            "text": body.decode("latin-1"),
        },
        trace_id="trace-pets",
        at=3,
        monotonic=3,
    )
    journal.append(
        "gateway-beta",
        "parser_input",
        {
            "text": "Available pets are:\n300 - the puppy",
            "bytes": len(body),
            "encoding": "latin-1",
            "transformations": [
                "normalize_newlines",
                "remove_ansi_sgr",
                "remove_blank_lines",
                "trim_lines",
            ],
            "wire_ref": {
                "source": "gateway-beta",
                "first_seq": wire.seq,
                "last_seq": wire.seq,
                "digest": digest,
            },
            "parser_version": "rules-2",
        },
        trace_id="trace-pets",
        at=3.5,
        monotonic=3.5,
    )
    journal.append(
        "gateway-beta",
        "observation",
        {
            "kind": "text",
            "text": "Available pets are:\n  300 - the puppy",
            "method": "ansi-stripped-lines",
        },
        trace_id="trace-pets",
        at=4,
        monotonic=4,
    )
    journal.close()
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get(
            f"/api/sessions/session-beta/wire/{wire.seq}"
        )
        investigation = await client.get(
            "/api/sessions/session-beta/investigation"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_id"] == f"gateway:{wire.seq}"
    assert payload["digest"] == digest
    assert payload["bytes"] == len(body)
    assert payload["content_text"] == body.decode()
    records = investigation.json()["records"]
    raw_record = next(record for record in records if record["id"] == f"gateway:{wire.seq}")
    parsed_record = next(
        record
        for record in records
        if record["source"] == "gateway"
        and record["kind"] == "observation"
        and record["trace_id"] == "trace-pets"
    )
    assert raw_record["parent_id"] is None
    assert parsed_record["fields"]["text"] == (
        "Available pets are:\n  300 - the puppy"
    )
    decoded_record = next(
        record
        for record in records
        if record["source"] == "gateway"
        and record["kind"] == "wire_text"
    )
    parser_input_record = next(
        record
        for record in records
        if record["source"] == "gateway"
        and record["kind"] == "parser_input"
    )
    assert "\u001b[32m" in decoded_record["fields"]["text"]
    assert parser_input_record["fields"]["text"] == (
        "Available pets are:\n300 - the puppy"
    )
    assert payload["content_base64"] != ""


def test_empty_gateway_database_is_a_valid_zero_event_capture(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    journal = (
        root
        / "profiles"
        / "beta"
        / "sessions"
        / "session-beta"
        / "gateway.db"
    )
    journal.unlink()
    journal.touch()

    assert RuntimeSource(root).events("session-beta") == []


async def test_each_selected_runtime_session_replays_only_its_own_evidence(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        alpha = await client.get("/api/sessions/session-alpha/replay?after=0")
        beta = await client.get("/api/sessions/session-beta/replay?after=0")

    assert alpha.status_code == 200
    assert "gateway-alpha" in alpha.text
    assert "gateway-beta" not in alpha.text
    assert '"cost_usd":0.11' in alpha.text
    assert beta.status_code == 200
    assert "gateway-beta" in beta.text
    assert "gateway-alpha" not in beta.text
    assert '"cost_usd":0.22' in beta.text


async def test_live_snapshot_joins_cost_to_the_selected_player_only(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        alpha = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()
        beta = (
            await client.get("/api/sessions/session-beta/snapshot")
        ).json()

    assert alpha["player_id"] == "alpha"
    assert alpha["objective"] == "Explore as Alpha"
    assert alpha["objective_initial"] == {
        "title": "Explore as Alpha",
        "clue": None,
        "source_kind": "operator",
        "revision": 1,
        "evidence": "agent log line 1",
    }
    assert alpha["objective_context"] == {
        "title": "Explore as Alpha",
        "clue": None,
        "source_kind": "operator",
        "revision": 1,
        "evidence": "agent log line 1",
    }
    assert alpha["suggested_action"] is None
    assert alpha["cost_usd"] == 0.11
    assert alpha["turn"] == 1
    assert alpha["iteration"] == 0
    assert alpha["context_limit"] == 200_000
    assert alpha["usage"]["fresh_input"] == 110
    assert alpha["player_status"]["fields"] == {}
    assert "hit" in alpha["player_status"]["capture_gaps"]
    assert alpha["spend_cap_usd"] is None
    assert beta["player_id"] == "beta"
    assert beta["objective"] == "Explore as Beta"
    assert beta["cost_usd"] == 0.22
    assert beta["usage"]["fresh_input"] == 220


async def test_historical_snapshot_is_the_exact_selected_prefix(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        first = (
            await client.get(
                "/api/sessions/session-alpha/snapshot?through=1"
            )
        ).json()
        latest = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()
        paused_at_latest = (
            await client.get(
                "/api/sessions/session-alpha/snapshot?through=2"
            )
        ).json()

    assert first["through_sequence"] == 1
    assert first["following_live"] is False
    assert first["objective"] == "Explore as Alpha"
    assert first["objective_initial"]["title"] == "Explore as Alpha"
    assert first["objective_context"]["title"] == "Explore as Alpha"
    assert first["turn"] is None
    assert "turn_not_observed" in first["capture_gaps"]
    assert first["context_limit"] == 200_000
    assert first["cost_usd"] == 0
    assert latest["through_sequence"] == 2
    assert latest["following_live"] is True
    assert paused_at_latest["through_sequence"] == 2
    assert paused_at_latest["following_live"] is False
    assert latest["turn"] == 1
    assert "turn_not_observed" not in latest["capture_gaps"]
    assert "context_limit_not_observed" not in latest["capture_gaps"]
    assert latest["cost_usd"] == 0.11


async def test_live_snapshot_separates_agent_thought_from_concise_belief(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    agent_log = (
        root
        / "profiles"
        / "alpha"
        / "sessions"
        / "session-alpha"
        / "agent.jsonl"
    )
    identity = {
        "player_id": "alpha",
        "agent_id": "agent-alpha",
        "session_id": "session-alpha",
        "gateway_session_id": "gateway-alpha",
    }
    with agent_log.open("a", encoding="utf-8") as handle:
        for event in (
            {
                "phase": "reasoning",
                "text": (
                    "A kobold blocks the alley east. I will fight through "
                    "before continuing toward Back Street."
                ),
                "redacted": False,
                "at": "1970-01-01T00:00:01.600+00:00",
                **identity,
            },
            {
                "phase": "tool_call",
                "name": "tbamud__move",
                "args": {"direction": "east"},
                "at": "1970-01-01T00:00:01.700+00:00",
                **identity,
            },
            {
                "phase": "operator_control",
                "request_id": "revise-objective",
                "action": "revise",
                "state": "running",
                "iteration": 1,
                "instruction": "Find the bakery",
                "at": "1970-01-01T00:00:01.800+00:00",
                **identity,
            },
        ):
            handle.write(json.dumps(event) + "\n")

    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        historical = (
            await client.get(
                "/api/sessions/session-alpha/snapshot?through=1"
            )
        ).json()
        latest = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()

    assert historical["agent_thought"] is None
    assert historical["agent_belief"] is None
    assert "agent_thought_not_observed" in historical["capture_gaps"]
    assert "agent_belief_not_observed" in historical["capture_gaps"]
    assert latest["agent_thought"] == {
        "text": (
            "A kobold blocks the alley east. I will fight through before "
            "continuing toward Back Street."
        ),
        "phase": "reasoning",
        "observed_at": "1970-01-01T00:00:01.600+00:00",
            "line": 6,
            "evidence": "agent log line 6",
    }
    assert latest["agent_belief"] == {
        "text": "Moving east",
        "phase": "tool_call",
        "observed_at": "1970-01-01T00:00:01.700+00:00",
            "line": 7,
            "evidence": "agent log line 7",
    }
    assert latest["objective"] == "Explore as Alpha"
    assert latest["objective_initial"] == {
        "title": "Explore as Alpha",
        "clue": None,
        "source_kind": "operator",
        "revision": 1,
        "evidence": "agent log line 1",
    }
    assert latest["objective_context"] == {
        "title": "Find the bakery",
        "clue": None,
        "source_kind": "operator",
        "revision": 2,
        "evidence": "agent log line 8",
    }
    assert "agent_thought_not_observed" not in latest["capture_gaps"]
    assert "agent_belief_not_observed" not in latest["capture_gaps"]


async def test_live_voice_uses_exact_thought_prefix_and_external_cache(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    thought = (
        "A kobold blocks the alley east. I will fight through before "
        "continuing toward Back Street."
    )
    with (session_dir / "agent.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "phase": "reasoning",
                    "text": thought,
                    "redacted": False,
                    "at": "1970-01-01T00:00:01.600+00:00",
                    "player_id": "alpha",
                    "agent_id": "agent-alpha",
                    "session_id": "session-alpha",
                    "gateway_session_id": "gateway-alpha",
                }
            )
            + "\n"
        )

    requests: list[httpx.Request] = []

    def synthesize(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert json.loads(request.content) == {
            "model": "tts-1",
            "voice": "nova",
            "input": thought,
            "response_format": "mp3",
        }
        return httpx.Response(
            200,
            content=b"mock-mp3-audio",
            headers={"Content-Type": "audio/mpeg"},
        )

    app = create_app(
        Settings(
            runtime_root=root,
            web_dist=tmp_path,
            voice_api_key="test-secret",
            voice_cache_root=root / "cache" / "observatory" / "voice",
        ),
        voice_transport=httpx.MockTransport(synthesize),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        capabilities = (await client.get("/api/capabilities")).json()
        historical = await client.post(
            "/api/sessions/session-alpha/voice",
            json={"expected_sequence": 1},
        )
        first = await client.post(
            "/api/sessions/session-alpha/voice",
            json={"expected_sequence": 2},
        )
        cached = await client.post(
            "/api/sessions/session-alpha/voice",
            json={"expected_sequence": 2},
        )

    assert capabilities["voice"] == {
        "enabled": True,
        "detail": (
            "Voice is available for the selected Agent thinking excerpt"
        ),
        "endpoint_template": "/api/sessions/{session}/voice",
        "max_characters": 400,
    }
    assert "live-voice" in capabilities["features"]
    assert historical.status_code == 409
    assert historical.json()["error"] == "voice_source_unavailable"
    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/mpeg"
    assert first.headers["x-voice-sequence"] == "2"
    assert first.content == b"mock-mp3-audio"
    assert cached.content == first.content
    assert len(requests) == 1
    cache_files = tuple((root / "cache" / "observatory" / "voice").glob("*.mp3"))
    assert len(cache_files) == 1
    assert cache_files[0].read_bytes() == b"mock-mp3-audio"


async def test_live_snapshot_exposes_observed_status_economics_and_frontier(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    journal = Journal(session_dir / "gateway.db")
    journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "player_state",
            "values": {
                "hit": 86,
                "mana": 61,
                "move": 84,
                "level": 3,
                "gold": 127,
                "posture": "standing",
                "hungry": False,
                "thirsty": False,
                "drunk": False,
                "poisoned": False,
            },
            "confidence": "high",
            "method": "score",
        },
        at=3,
        monotonic=3,
    )
    journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "player_state",
            "values": {"hit": 72, "level": 4},
            "confidence": "high",
            "method": "score",
        },
        at=4,
        monotonic=4,
    )
    journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "room",
            "title": "North Gate",
            "exits": ["west", "east"],
        },
        trace_id="trace-north-gate",
        at=5,
        monotonic=5,
    )
    journal.append(
        "gateway-alpha",
        "position",
        {
            "place": 3042,
            "title": "North Gate",
            "confidence": "high",
            "method": "room-id",
        },
        trace_id="trace-north-gate",
        at=6,
        monotonic=6,
    )
    journal.append(
        "gateway-alpha",
        "parse_metric",
        {"cumulative_miss_rate": 0},
        at=7,
        monotonic=7,
    )
    journal.close()
    identity = {
        "player_id": "alpha",
        "agent_id": "agent-alpha",
        "session_id": "session-alpha",
        "gateway_session_id": "gateway-alpha",
    }
    with (session_dir / "agent.jsonl").open("a", encoding="utf-8") as handle:
        for record in (
            {
                "phase": "session_start",
                "model": "test-model",
                "max_total_cost_usd": 0.5,
                "context_window": 200_000,
                "at": "1970-01-01T00:00:02.500+00:00",
                **identity,
            },
            {
                "phase": "turn",
                "at": "1970-01-01T00:00:03+00:00",
                **identity,
            },
            {
                "phase": "response",
                "model": "test-model",
                "cost_usd": 0.02,
                "usage": {
                    "input_tokens": 240,
                    "cache_read_input_tokens": 80,
                    "output_tokens": 12,
                },
                "at": "1970-01-01T00:00:03.500+00:00",
                **identity,
            },
            {
                "phase": "response",
                "model": "test-model",
                "cost_usd": 0.03,
                "usage": {
                    "input_tokens": 90,
                    "cache_read_input_tokens": 10,
                    "output_tokens": 8,
                },
                "at": "1970-01-01T00:00:06.500+00:00",
                **identity,
            },
            {
                "phase": "turn_end",
                "reason": "completed",
                "at": "1970-01-01T00:00:06.750+00:00",
                **identity,
            },
        ):
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        historical = (
            await client.get(
                "/api/sessions/session-alpha/snapshot?through=3"
            )
        ).json()
        snapshot = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()

    assert historical["player_status"]["fields"]["hit"]["value"] == 86
    assert historical["player_status"]["fields"]["level"]["value"] == 3
    assert historical["milestones"] == []
    assert historical["current_turn_cost_usd"] == 0
    assert historical["agent_turn_active"] is True
    assert historical["economics"][-1]["cumulative_cost_usd"] == 0.11
    status = snapshot["player_status"]
    assert status["fields"]["hit"]["value"] == 72
    assert status["fields"]["hit"]["sequence"] == 4
    assert status["fields"]["gold"]["value"] == 127
    assert status["capture_gaps"] == []
    assert snapshot["spend_cap_usd"] == 0.5
    assert snapshot["spend_cap_scope"] == "session"
    assert snapshot["current_turn_cost_usd"] == 0.05
    assert snapshot["agent_turn_active"] is False
    assert snapshot["turn"] == 3
    assert snapshot["context_limit"] == 200_000
    assert snapshot["economics"][-1]["context_tokens"] == 100
    assert snapshot["room_economics"] == [{
        "node_id": "place:3042",
        "response_count": 1,
        "cost_usd": 0.03,
        "first_response": 3,
        "last_response": 3,
        "evidence": [
            "agent log line 9; gateway position seq 6",
        ],
    }]
    assert snapshot["unattributed_room_economics"]["response_count"] == 2
    assert snapshot["unattributed_room_economics"]["cost_usd"] == 0.13
    assert snapshot["milestones"] == [{
        "kind": "level_up",
        "sequence": 4,
        "at": 4.0,
        "previous": 3,
        "current": 4,
        "evidence": "gateway observation seq 4",
    }]
    assert {
        (item["source"], item["direction"])
        for item in snapshot["world"]["frontier"]
    } == {
        ("place:3042", "east"),
        ("place:3042", "west"),
    }


async def test_live_ask_uses_only_selected_runtime_scope(tmp_path: Path):
    root = runtime_root(tmp_path)
    benchmark = tmp_path / "unrelated-benchmark"
    benchmark.mkdir()
    app = create_app(
        Settings(
            runtime_root=root,
            benchmark_root=benchmark,
            web_dist=tmp_path,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "Why did the agent stop?",
                "scope": {
                    "space": "live",
                    "player_id": "alpha",
                    "live_session_id": "session-alpha",
                    "through_sequence": 1,
                },
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["tier"] == "deterministic"
    assert result["query"]["scope"]["space"] == "live"
    assert [step["source"] for step in result["plan"]] == ["runtime"]
    assert all(citation["source"] != "benchmark" for citation in result["citations"])
    assert "has not stopped" in result["answer"]


async def test_sessions_ask_diagnoses_a_launcher_runtime_by_run_id(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "Why did the session stop?",
                "scope": {
                    "space": "sessions",
                    "player_id": "beta",
                    "run_id": "session-beta",
                },
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["tier"] == "deterministic"
    assert result["query"]["scope"]["run_id"] == "session-beta"
    assert result["plan"][0]["source"] == "runtime"
    assert "lifecycle state stopped" in result["answer"]
    assert result["citations"][0]["id"] == "runtime:session:session-beta"
    assert result["missing"] == ["specific stop mode"]


async def test_sessions_ask_searches_runtime_agent_and_gateway_records(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "Find Explore as Alpha",
                "scope": {
                    "space": "sessions",
                    "player_id": "alpha",
                    "run_id": "session-alpha",
                },
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["tier"] == "deterministic"
    assert result["plan"][0]["source"] == "runtime"
    assert result["citations"]
    assert all(
        citation["source"] in {"agent", "gateway"}
        for citation in result["citations"]
    )


async def test_live_ask_rejects_player_and_session_mismatch(tmp_path: Path):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "What is happening now?",
                "scope": {
                    "space": "live",
                    "player_id": "beta",
                    "live_session_id": "session-alpha",
                },
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["citations"] == []
    assert result["missing"] == [
        "runtime session matching the selected player"
    ]


async def test_exact_query_cannot_replace_active_scope(tmp_path: Path):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "Search the current evidence",
                "scope": {
                    "space": "live",
                    "player_id": "alpha",
                    "live_session_id": "session-alpha",
                },
                "query": {
                    "version": 1,
                    "operation": "search_evidence",
                    "scope": {
                        "space": "live",
                        "player_id": "beta",
                        "live_session_id": "session-beta",
                    },
                },
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["tier"] == "unsupported"
    assert result["plan"][0]["operation"] == "validate_scope"
    assert result["citations"] == []


async def test_operation_cannot_escape_selected_space(tmp_path: Path):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "Compare this runtime",
                "scope": {
                    "space": "live",
                    "player_id": "alpha",
                    "live_session_id": "session-alpha",
                },
                "query": {
                    "version": 1,
                    "operation": "compare_rendering",
                    "scope": {
                        "space": "live",
                        "player_id": "alpha",
                        "live_session_id": "session-alpha",
                    },
                },
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["tier"] == "unsupported"
    assert result["plan"][0]["operation"] == "validate_scope"
    assert result["citations"] == []


async def test_filter_operator_must_match_the_selected_field(tmp_path: Path):
    root = runtime_root(tmp_path)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "Find a cost containing one",
                "scope": {
                    "space": "live",
                    "player_id": "alpha",
                    "live_session_id": "session-alpha",
                },
                "query": {
                    "version": 1,
                    "operation": "search_evidence",
                    "scope": {
                        "space": "live",
                        "player_id": "alpha",
                        "live_session_id": "session-alpha",
                    },
                    "filters": [{
                        "field": "cost_usd",
                        "operator": "contains",
                        "value": "1",
                    }],
                },
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["tier"] == "unsupported"
    assert result["plan"][0]["operation"] == "validate_scope"
    assert "cost_usd:contains" in result["plan"][0]["detail"]
    assert result["citations"] == []


async def test_model_translation_cannot_escape_selected_live_scope(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)

    async def translator(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": '{"operation":"compare_rendering"}',
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 4},
            },
        )

    app = create_app(
        Settings(
            runtime_root=root,
            web_dist=tmp_path,
            copilot_model="test-model",
            copilot_api_key="test-token",
            copilot_spend_cap=0.1,
            copilot_input_rate=1,
            copilot_output_rate=5,
        ),
        copilot_transport=httpx.MockTransport(translator),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "Give me a totally novel autopsy",
                "scope": {
                    "space": "live",
                    "player_id": "alpha",
                    "live_session_id": "session-alpha",
                },
                "allow_model": True,
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["tier"] == "unsupported"
    assert result["query"]["operation"] == "compare_rendering"
    assert result["plan"][0]["operation"] == "validate_scope"
    assert result["citations"] == []


async def test_supported_local_query_never_calls_the_optional_model(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    calls = 0

    async def translator(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    app = create_app(
        Settings(
            runtime_root=root,
            web_dist=tmp_path,
            copilot_model="test-model",
            copilot_api_key="test-token",
            copilot_spend_cap=0.1,
            copilot_input_rate=1,
            copilot_output_rate=5,
        ),
        copilot_transport=httpx.MockTransport(translator),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.post(
            "/api/ask",
            json={
                "question": "Show the current agent status.",
                "scope": {
                    "space": "live",
                    "player_id": "alpha",
                    "live_session_id": "session-alpha",
                },
                "allow_model": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["tier"] == "deterministic"
    assert calls == 0


async def test_operator_guidance_and_revised_goal_are_visible_evidence(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    log = (
        root
        / "profiles"
        / "alpha"
        / "sessions"
        / "session-alpha"
        / "agent.jsonl"
    )
    identity = {
        "player_id": "alpha",
        "agent_id": "agent-alpha",
        "session_id": "session-alpha",
        "gateway_session_id": "gateway-alpha",
    }
    with log.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "phase": "operator_control",
                    "action": "revise",
                    "instruction": "Find and fight Fido",
                    "at": "1970-01-01T00:00:01.750+00:00",
                    **identity,
                }
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "phase": "prompt",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Explore as Alpha"}
                            ],
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Find and fight Fido",
                                }
                            ],
                        },
                    ],
                    "at": "1970-01-01T00:00:01.800+00:00",
                    **identity,
                }
            )
            + "\n"
        )
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        snapshot = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()

    assert snapshot["objective"] == "Find and fight Fido"
    operator_item = next(
        item
        for item in snapshot["timeline"]
        if item["label"] == "Operator revise: Find and fight Fido"
    )
    assert operator_item["sequence"] == 2


async def test_running_session_stream_observes_a_new_journal_event(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        pending = asyncio.create_task(
            client.get(
                "/api/sessions/session-alpha/events?after=2&limit=1"
            )
        )
        await asyncio.sleep(0.15)
        journal = Journal(session_dir / "gateway.db")
        journal.append(
            "gateway-alpha",
            "position",
            {
                "place": 3001,
                "title": "The Temple Of Midgaard",
                "confidence": "high",
                "method": "room-id",
            },
            at=3,
            monotonic=3,
        )
        journal.close()
        response = await asyncio.wait_for(pending, timeout=2)

    assert response.status_code == 200
    assert "gateway-alpha" in response.text
    assert "gateway-beta" not in response.text
    assert "The Temple Of Midgaard" in response.text


async def test_control_targets_only_the_selected_live_agent(tmp_path: Path):
    root = runtime_root(tmp_path)
    digest = hashlib.sha256("session-alpha".encode()).hexdigest()[:20]
    socket_path = (
        Path(tempfile.gettempdir()) / f"boukensha-{digest}-operator.sock"
    )
    received: list[dict] = []

    def serve() -> None:
        socket_path.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(socket_path))
            server.listen(1)
            connection, _ = server.accept()
            with connection:
                request = json.loads(connection.recv(65_536))
                received.append(request)
                connection.sendall(
                    (
                        json.dumps(
                            {
                                "ok": True,
                                "request_id": request["request_id"],
                                "action": request["action"],
                                "state": "running",
                                "insertion": "next_iteration_boundary",
                            }
                        )
                        + "\n"
                    ).encode()
                )
        socket_path.unlink(missing_ok=True)

    worker = threading.Thread(target=serve)
    worker.start()
    for _ in range(100):
        if socket_path.exists():
            break
        await asyncio.sleep(0.01)
    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        catalog = (await client.get("/api/sessions")).json()
        response = await client.post(
            "/api/sessions/session-alpha/control",
            json={
                "request_id": "operator-request-1",
                "action": "guide",
                "instruction": "Look east",
                "expected_sequence": 2,
            },
        )
        stale = await client.post(
            "/api/sessions/session-alpha/control",
            json={
                "request_id": "operator-request-2",
                "action": "pause",
                "expected_sequence": 1,
            },
        )
        ended = await client.post(
            "/api/sessions/session-beta/control",
            json={
                "request_id": "operator-request-3",
                "action": "pause",
                "expected_sequence": 2,
            },
        )
    worker.join(timeout=2)

    assert response.status_code == 200
    assert catalog["sessions"][0]["control_available"] is True
    assert response.json()["insertion"] == "next_iteration_boundary"
    assert received[0]["player_id"] == "alpha"
    assert received[0]["session_id"] == "session-alpha"
    assert received[0]["token"] == "token-alpha"
    assert "beta" not in json.dumps(received)
    assert stale.status_code == 409
    assert "advanced" in stale.json()["detail"]
    assert ended.status_code == 409
    assert "not live" in ended.json()["detail"]


def test_registry_paths_cannot_escape_the_player_session_layout(tmp_path: Path):
    root = runtime_root(tmp_path)
    database = sqlite3.connect(root / "registry.db")
    database.execute(
        "UPDATE sessions SET session_dir = ? WHERE session_id = ?",
        (str(tmp_path), "session-alpha"),
    )
    database.commit()
    database.close()

    source = RuntimeSource(root)
    try:
        source.sessions()
    except RuntimeSourceError as error:
        assert "violates the runtime layout" in str(error)
    else:
        raise AssertionError("unsafe registry path was accepted")


def test_gateway_quarantine_dominates_operator_pause(tmp_path: Path):
    (tmp_path / "operator-state.json").write_text(
        json.dumps({"state": "paused"}),
        encoding="utf-8",
    )
    (tmp_path / "control-state.json").write_text(
        json.dumps({"state": "quarantined"}),
        encoding="utf-8",
    )

    assert RuntimeSource._control_state(tmp_path) == "quarantined"


async def test_combat_episode_uses_correlated_command_and_terminal_evidence(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    journal = Journal(session_dir / "gateway.db")
    command = journal.append(
        "gateway-alpha",
        "command",
        {"line": "kill a large kobold"},
        trace_id="trace-combat",
        at=3,
        monotonic=3,
    )
    first = journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "combat",
            "text": "You hit a large kobold hard.",
            "confidence": "medium",
            "method": "combat-colour-or-verb",
        },
        trace_id="trace-combat",
        at=3.1,
        monotonic=3.1,
    )
    journal.append(
        "gateway-alpha",
        "command",
        {"line": "look"},
        trace_id="trace-look",
        at=3.15,
        monotonic=3.15,
    )
    after_look = journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "room",
            "text": "The kobold is here, fighting YOU!",
            "confidence": "high",
            "method": "ansi-title+room-frame",
        },
        trace_id="trace-look",
        at=3.16,
        monotonic=3.16,
    )
    unrelated = journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "unparsed",
            "text": "A sewer rat is dead!",
            "confidence": "low",
            "method": "unmatched-colour:none",
        },
        trace_id="trace-combat",
        at=3.2,
        monotonic=3.2,
    )
    terminal = journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "unparsed",
            "text": "A large kobold is dead!",
            "confidence": "low",
            "method": "unmatched-colour:none",
        },
        trace_id="trace-combat",
        at=3.3,
        monotonic=3.3,
    )
    journal.close()

    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        before_terminal = (
            await client.get(
                f"/api/sessions/session-alpha/snapshot"
                f"?through={unrelated.seq}"
            )
        ).json()
        completed = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()

    assert before_terminal["combat"] is True
    assert before_terminal["combat_episode"]["active"] is True
    assert first.seq in before_terminal["combat_episode"]["evidence"]
    assert after_look.seq not in before_terminal["combat_episode"]["evidence"]
    assert completed["combat"] is False
    assert completed["combat_episode"] == {
        "active": False,
        "opponent": "a large kobold",
        "first_observed_turn": 1,
        "observed_exchanges": 1,
        "outcome": "victory",
        "command_trace": "trace-combat",
        "lines": [
            {
                "text": "You hit a large kobold hard.",
                "sequence": first.seq,
                "observed_at": 3.1,
                "confidence": "medium",
                "method": "combat-colour-or-verb",
                "evidence": f"gateway observation seq {first.seq}",
            }
        ],
        "evidence": [command.seq, first.seq, terminal.seq],
    }


async def test_combat_episode_supports_mob_start_switch_and_flee(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    journal = Journal(session_dir / "gateway.db")
    mob_start = journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "combat",
            "text": "A sewer rat bites you.",
            "confidence": "medium",
            "method": "combat-colour-or-verb",
        },
        trace_id="trace-mob",
        at=3,
        monotonic=3,
    )
    journal.append(
        "gateway-alpha",
        "command",
        {"line": "kill a large kobold"},
        trace_id="trace-switch",
        at=4,
        monotonic=4,
    )
    switched = journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "combat",
            "text": "A large kobold claws you.",
            "confidence": "medium",
            "method": "combat-colour-or-verb",
        },
        trace_id="trace-switch",
        at=4.1,
        monotonic=4.1,
    )
    fled = journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "unparsed",
            "text": "A large kobold panics, and attempts to flee!",
            "confidence": "low",
            "method": "unmatched-colour:none",
        },
        trace_id="trace-switch",
        at=4.2,
        monotonic=4.2,
    )
    journal.close()

    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        mob = (
            await client.get(
                f"/api/sessions/session-alpha/snapshot?through={mob_start.seq}"
            )
        ).json()["combat_episode"]
        completed = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()["combat_episode"]

    assert mob["active"] is True
    assert mob["opponent"] is None
    assert mob["command_trace"] is None
    assert completed["active"] is False
    assert completed["opponent"] == "a large kobold"
    assert completed["observed_exchanges"] == 2
    assert completed["lines"][-1]["sequence"] == switched.seq
    assert completed["outcome"] == "fled"
    assert fled.seq in completed["evidence"]


async def test_active_combat_at_capture_end_is_unresolved(tmp_path: Path):
    root = runtime_root(tmp_path)
    session_dir = root / "profiles" / "beta" / "sessions" / "session-beta"
    journal = Journal(session_dir / "gateway.db")
    combat = journal.append(
        "gateway-beta",
        "observation",
        {
            "kind": "combat",
            "text": "A wolf bites you.",
            "confidence": "medium",
            "method": "combat-colour-or-verb",
        },
        trace_id="trace-capture-end",
        at=3,
        monotonic=3,
    )
    journal.close()

    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        snapshot = (
            await client.get("/api/sessions/session-beta/snapshot")
        ).json()

    assert snapshot["combat"] is False
    assert snapshot["combat_episode"]["active"] is False
    assert snapshot["combat_episode"]["outcome"] == "unresolved"
    assert snapshot["combat_episode"]["evidence"] == [combat.seq]


async def test_combat_episode_switches_only_on_correlated_combat(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    journal = Journal(session_dir / "gateway.db")
    journal.append(
        "gateway-alpha",
        "command",
        {"line": "kill sewer rat"},
        trace_id="trace-rat",
        at=3,
        monotonic=3,
    )
    journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "combat",
            "text": "A sewer rat bites you.",
            "confidence": "medium",
            "method": "combat-colour-or-verb",
        },
        trace_id="trace-rat",
        at=3.1,
        monotonic=3.1,
    )
    journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "unparsed",
            "text": "A sewer pirate is dead!",
            "confidence": "low",
            "method": "unmatched-colour:none",
        },
        trace_id="trace-rat",
        at=3.2,
        monotonic=3.2,
    )
    switch_command = journal.append(
        "gateway-alpha",
        "command",
        {"line": "kill a large kobold"},
        trace_id="trace-kobold",
        at=4,
        monotonic=4,
    )
    switch_line = journal.append(
        "gateway-alpha",
        "observation",
        {
            "kind": "combat",
            "text": "A large kobold claws you.",
            "confidence": "medium",
            "method": "combat-colour-or-verb",
        },
        trace_id="trace-kobold",
        at=4.1,
        monotonic=4.1,
    )
    journal.close()

    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        snapshot = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()

    episode = snapshot["combat_episode"]
    assert episode["active"] is True
    assert episode["opponent"] == "a large kobold"
    assert episode["command_trace"] == "trace-kobold"
    assert episode["observed_exchanges"] == 1
    assert episode["lines"][0]["sequence"] == switch_line.seq
    assert episode["evidence"] == [switch_command.seq, switch_line.seq]


async def test_zone_follows_verified_reset_and_directional_atlas_chain(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    world = tmp_path / "world" / "wld"
    zones = tmp_path / "world" / "zon"
    world.mkdir(parents=True)
    zones.mkdir()
    (world / "7.wld").write_text(
        "#100\nReset Room~\nDescription\n~\n7 0 0\n"
        "D1\nEast~\n~\n0 0 101\nS\n"
        "#101\nTarget Room~\nDescription\n~\n7 0 0\n"
        "D3\nWest~\n~\n0 0 100\nS\n$\n",
        encoding="utf-8",
    )
    (zones / "7.zon").write_text(
        "#7\nMidgaard~\n700 799 15 2\nS\n$\n",
        encoding="utf-8",
    )
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    journal = Journal(session_dir / "gateway.db")
    reset = journal.append(
        "gateway-alpha",
        "reset_receipt",
        {
            "ok": True,
            "verified_room_vnum": 100,
            "verified_room_title": "Reset Room",
        },
        at=3,
        monotonic=3,
    )
    command = journal.append(
        "gateway-alpha",
        "command",
        {"line": "east"},
        trace_id="trace-east",
        at=4,
        monotonic=4,
    )
    position = journal.append(
        "gateway-alpha",
        "position",
        {
            "place": 2,
            "title": "Target Room",
            "confidence": "high",
            "method": "room-frame",
        },
        trace_id="trace-east",
        at=4.1,
        monotonic=4.1,
    )
    journal.append(
        "gateway-alpha",
        "command",
        {"line": "north"},
        trace_id="trace-broken",
        at=5,
        monotonic=5,
    )
    journal.append(
        "gateway-alpha",
        "position",
        {
            "place": 3,
            "title": "Uncorrelated Room",
            "confidence": "medium",
            "method": "topology",
        },
        trace_id="trace-broken",
        at=5.1,
        monotonic=5.1,
    )
    journal.close()

    app = create_app(
        Settings(runtime_root=root, world_root=world, web_dist=tmp_path)
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        correlated = (
            await client.get(
                f"/api/sessions/session-alpha/snapshot"
                f"?through={position.seq}"
            )
        ).json()
        broken = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()

    assert correlated["zone"] == {
        "zone_id": 7,
        "label": "Midgaard",
        "room_vnum": 101,
        "sector": "inside",
        "form": "truth",
        "confidence": "medium",
        "reset_sequence": reset.seq,
        "movement_sequences": [command.seq, position.seq],
        "atlas_digest": correlated["zone"]["atlas_digest"],
        "evidence": [
            f"gateway reset receipt seq {reset.seq}",
            (
                f"gateway movement command seq {command.seq} "
                f"and position seq {position.seq}"
            ),
        ],
    }
    assert len(correlated["zone"]["atlas_digest"]) == 20
    target_node = next(
        node for node in correlated["world"]["nodes"]
        if node["place"] == 2
    )
    assert target_node["atlas"] == {
        "vnum": 101,
        "zone_id": 7,
        "zone_label": "Midgaard",
        "sector": "inside",
        "atlas_digest": correlated["zone"]["atlas_digest"],
        "confidence": "medium",
        "evidence": correlated["zone"]["evidence"],
    }
    assert "zone_not_observed" not in correlated["capture_gaps"]
    assert broken["zone"] is None
    assert "zone_not_observed" in broken["capture_gaps"]


async def test_world_atlas_correlation_recovers_repeated_synthetic_places(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    world = tmp_path / "world" / "wld"
    zones = tmp_path / "world" / "zon"
    world.mkdir(parents=True)
    zones.mkdir()
    (world / "7.wld").write_text(
        "#100\nAnchor Room~\nDescription\n~\n7 0 0\n"
        "D1\nEast~\n~\n0 0 101\nS\n"
        "#101\nTarget Room~\nDescription\n~\n7 0 0\n"
        "D3\nWest~\n~\n0 0 100\nS\n$\n",
        encoding="utf-8",
    )
    (zones / "7.zon").write_text(
        "#7\nMidgaard~\n700 799 15 2\nS\n$\n",
        encoding="utf-8",
    )
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    journal = Journal(session_dir / "gateway.db")
    rows = (
        (
            "observation",
            {"kind": "room", "title": "Anchor Room", "exits": ["east"]},
            "trace-anchor",
        ),
        (
            "position",
            {
                "place": 1,
                "title": "Anchor Room",
                "confidence": "tracked",
                "method": "new-title",
            },
            "trace-anchor",
        ),
        ("command", {"line": "east"}, "trace-east"),
        (
            "observation",
            {"kind": "room", "title": "Target Room", "exits": ["west"]},
            "trace-east",
        ),
        (
            "position",
            {
                "place": 2,
                "title": "Target Room",
                "confidence": "tracked",
                "method": "new-arrival-path",
            },
            "trace-east",
        ),
        ("command", {"line": "west"}, "trace-west"),
        (
            "observation",
            {"kind": "room", "title": "Anchor Room", "exits": ["east"]},
            "trace-west",
        ),
        (
            "position",
            {
                "place": 3,
                "title": "Anchor Room",
                "confidence": "tracked",
                "method": "new-arrival-path",
            },
            "trace-west",
        ),
    )
    for index, (kind, payload, trace_id) in enumerate(rows, start=1):
        journal.append(
            "gateway-alpha",
            kind,
            payload,
            trace_id=trace_id,
            at=float(index),
            monotonic=float(index),
        )
    journal.close()

    app = create_app(
        Settings(runtime_root=root, world_root=world, web_dist=tmp_path)
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        snapshot = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()

    vnums = {
        node["place"]: node["atlas"]["vnum"]
        for node in snapshot["world"]["nodes"]
    }
    assert vnums == {1: 100, 2: 101, 3: 100}


async def test_destination_action_requires_beacon_and_learned_route(
    tmp_path: Path,
):
    root = runtime_root(tmp_path)
    session_dir = (
        root / "profiles" / "alpha" / "sessions" / "session-alpha"
    )
    journal = Journal(session_dir / "gateway.db")
    rows = (
        (
            "observation",
            {
                "kind": "room",
                "title": "Temple Square",
                "exits": ["east"],
                "mobs": [],
                "objects": [],
            },
            "trace-temple",
        ),
        (
            "position",
            {
                "place": 1,
                "title": "Temple Square",
                "confidence": "high",
                "method": "room-frame",
            },
            "trace-temple",
        ),
        ("command", {"line": "east"}, "trace-east"),
        (
            "observation",
            {
                "kind": "room",
                "title": "Minotaur Lair",
                "exits": ["west"],
                "mobs": ["Massive Minotaur"],
                "objects": [],
            },
            "trace-east",
        ),
        (
            "position",
            {
                "place": 2,
                "title": "Minotaur Lair",
                "confidence": "high",
                "method": "room-frame",
            },
            "trace-east",
        ),
        ("command", {"line": "west"}, "trace-west"),
        (
            "observation",
            {
                "kind": "room",
                "title": "Temple Square",
                "exits": ["east"],
                "mobs": [],
                "objects": [],
            },
            "trace-west",
        ),
        (
            "position",
            {
                "place": 1,
                "title": "Temple Square",
                "confidence": "high",
                "method": "room-frame",
            },
            "trace-west",
        ),
    )
    written = [
        journal.append(
            "gateway-alpha",
            kind,
            payload,
            trace_id=trace,
            at=3 + index / 10,
            monotonic=3 + index / 10,
        )
        for index, (kind, payload, trace) in enumerate(rows)
    ]
    journal.close()
    agent_log = session_dir / "agent.jsonl"
    identity = {
        "player_id": "alpha",
        "agent_id": "agent-alpha",
        "session_id": "session-alpha",
        "gateway_session_id": "gateway-alpha",
    }
    with agent_log.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "phase": "prompt",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Find the Massive Minotaur",
                                }
                            ],
                        }
                    ],
                    "at": "1970-01-01T00:00:02.500+00:00",
                    **identity,
                }
            )
            + "\n"
        )

    app = create_app(Settings(runtime_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        snapshot = (
            await client.get("/api/sessions/session-alpha/snapshot")
        ).json()

    action = snapshot["suggested_action"]
    assert action["kind"] == "route"
    assert action["label"] == "Head to Massive Minotaur"
    assert action["instruction"] == (
        "Follow the learned route toward Massive Minotaur: east."
    )
    assert action["expected_sequence"] == written[-1].seq
    assert f"objective beacon seq {written[4].seq}" in action["evidence"]
    assert f"gateway transition seq {written[4].seq}" in action["evidence"]
    assert snapshot["recent_path"] == {
        "edge_ids": [
            f"1:2:east",
            f"2:1:west",
        ],
        "gateway_sequences": [
            written[4].seq,
            written[7].seq,
        ],
    }


def test_measured_runs_are_visible_too(tmp_path: Path):
    """A run nobody can watch is a run nobody can check.

    A benchmark keeps its own tree so it cannot disturb the player it
    measures. That isolation is about writing, not about looking.
    """
    root = runtime_root(tmp_path)
    attempt = root / "benchmarks" / "minotaur" / "attempts" / "01"
    attempt.mkdir(parents=True)
    database = sqlite3.connect(attempt / "registry.db")
    database.executescript(REGISTRY_SCHEMA)
    database.close()
    add_session(
        attempt,
        player="alpha",
        character="Alpha",
        session="session-measured",
        gateway_session="gateway-measured",
        state="stopped",
        cost=0.05,
    )

    found = {session.id for session in RuntimeSource(root).sessions()}

    assert "session-measured" in found
    assert {"session-alpha", "session-beta"} <= found


def test_a_measured_session_reads_from_its_own_tree(tmp_path: Path):
    """Its files live under the run, not under the player being measured."""
    root = runtime_root(tmp_path)
    attempt = root / "benchmarks" / "minotaur" / "attempts" / "01"
    attempt.mkdir(parents=True)
    database = sqlite3.connect(attempt / "registry.db")
    database.executescript(REGISTRY_SCHEMA)
    database.close()
    add_session(
        attempt,
        player="alpha",
        character="Alpha",
        session="session-measured",
        gateway_session="gateway-measured",
        state="stopped",
        cost=0.05,
    )

    source = RuntimeSource(root)
    session = source.session("session-measured")

    assert session is not None
    assert str(attempt) in str(source._session_dir("session-measured"))


def test_a_running_row_whose_process_is_gone_is_not_live(tmp_path: Path) -> None:
    """A run killed outright never writes its ending, so its row keeps
    saying it runs. Believing the row showed a session as live for two
    days after the process owning it had gone."""
    root = tmp_path / ".boukensha"
    root.mkdir()
    database = sqlite3.connect(root / "registry.db")
    database.executescript(REGISTRY_SCHEMA)
    database.close()
    add_session(
        root,
        player="ghost",
        character="Ghost",
        session="session-ghost",
        gateway_session="gateway-ghost",
        state="running",
        cost=0.0,
        pid=999_999_999,
    )
    source = RuntimeSource(root)
    sessions = {session.id: session for session in source.sessions()}

    ghost = sessions["session-ghost"]
    assert ghost.state == "running", "the row still claims to be running"
    assert ghost.live is False, "and it is not believed"


def test_a_running_row_with_a_live_process_is_live(tmp_path: Path) -> None:
    root = tmp_path / ".boukensha"
    root.mkdir()
    database = sqlite3.connect(root / "registry.db")
    database.executescript(REGISTRY_SCHEMA)
    database.close()
    add_session(
        root,
        player="here",
        character="Here",
        session="session-here",
        gateway_session="gateway-here",
        state="running",
        cost=0.0,
        pid=os.getpid(),
    )
    source = RuntimeSource(root)
    sessions = {session.id: session for session in source.sessions()}

    assert sessions["session-here"].live is True
