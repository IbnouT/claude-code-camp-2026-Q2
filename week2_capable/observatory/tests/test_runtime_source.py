from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import sqlite3
import tempfile
import threading
from pathlib import Path

import httpx
from mud_gateway.journal import Journal

from observatory_api.app import create_app
from observatory_api.settings import Settings
from observatory_api.sources.runtime import RuntimeSource, RuntimeSourceError


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


def add_session(
    root: Path,
    *,
    player: str,
    character: str,
    session: str,
    gateway_session: str,
    state: str,
    cost: float,
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
                    "phase": "response",
                    "model": "test-model",
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
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, NULL, ?, ?, ?, 0, ?, 0)
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
    assert payload["sessions"][1]["live"] is False
    sources = {
        source["id"]: source
        for source in capabilities.json()["sources"]
    }
    assert sources["agent"]["state"] == "ready"


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
    assert alpha["cost_usd"] == 0.11
    assert alpha["usage"]["fresh_input"] == 110
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

    assert first["through_sequence"] == 1
    assert first["following_live"] is False
    assert first["objective"] == "Explore as Alpha"
    assert first["cost_usd"] == 0
    assert latest["through_sequence"] == 2
    assert latest["following_live"] is True
    assert latest["cost_usd"] == 0.11


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
    assert any(
        item["label"] == "Operator revise: Find and fight Fido"
        for item in snapshot["timeline"]
    )


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
