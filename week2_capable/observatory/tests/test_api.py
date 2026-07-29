from __future__ import annotations

import json
import sqlite3

import httpx

from observatory_api.app import create_app
from observatory_api.projections.parser_replay import replay_parser
from observatory_api.projections.world import project_world
from observatory_api.settings import Settings
from observatory_api.sources.comparison import rendering_comparison


async def test_health_is_read_only(tmp_path):
    app = create_app(Settings(web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/health")
    assert response.json() == {"status": "ok", "read_only": True}


async def test_capabilities_are_honest_when_sources_are_absent(tmp_path):
    app = create_app(
        Settings(
            gateway_url="http://127.0.0.1:1",
            web_dist=tmp_path,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/capabilities")
    sources = {item["id"]: item for item in response.json()["sources"]}
    assert sources["gateway"]["state"] == "unavailable"
    assert sources["knowledge"]["state"] == "disabled"


async def test_missing_frontend_has_a_setup_action(tmp_path):
    app = create_app(Settings(web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/")
    assert response.status_code == 503
    assert response.json()["error"] == "frontend_not_built"


async def test_built_frontend_assets_are_served(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "index.html").write_text("<main>observatory</main>")
    (assets / "app.js").write_text("export const ready = true")
    app = create_app(Settings(web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        index = await client.get("/")
        asset = await client.get("/assets/app.js")
        missing = await client.get("/assets/not-there.js")
    assert index.status_code == 200
    assert asset.status_code == 200
    assert "ready = true" in asset.text
    assert missing.status_code == 404


async def test_gateway_sessions_are_proxied_without_rewriting(tmp_path):
    async def gateway(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sessions"
        return httpx.Response(200, json={"sessions": ["s1", "s2"]})

    app = create_app(
        Settings(gateway_url="http://gateway", web_dist=tmp_path),
        gateway_transport=httpx.MockTransport(gateway),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/sessions")
    assert response.json() == {"sessions": ["s1", "s2"]}


async def test_gateway_contracts_are_proxied_without_rewriting(tmp_path):
    canonical = {
        "event": {
            "type": "object",
            "required": ["seq", "session", "at", "kind", "trace_id", "data"],
        }
    }

    async def gateway(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/contracts"
        return httpx.Response(200, json=canonical)

    app = create_app(
        Settings(gateway_url="http://gateway", web_dist=tmp_path),
        gateway_transport=httpx.MockTransport(gateway),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/contracts")
    assert response.json() == canonical


async def test_live_and_replay_sse_remain_byte_equivalent(tmp_path):
    canonical = (
        'id: 1\nevent: observation\ndata: {"seq":1,"session":"s1",'
        '"at":1.0,"kind":"observation","trace_id":null,'
        '"data":{"kind":"room","title":"Temple"}}\n\n'
    ).encode()

    async def gateway(request: httpx.Request) -> httpx.Response:
        assert request.url.params["after"] == "0"
        return httpx.Response(
            200,
            stream=httpx.ByteStream(canonical),
            headers={"content-type": "text/event-stream"},
        )

    app = create_app(
        Settings(gateway_url="http://gateway", web_dist=tmp_path),
        gateway_transport=httpx.MockTransport(gateway),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        replay = await client.get("/api/sessions/s1/replay?after=0")
        live = await client.get("/api/sessions/s1/events?after=0")
    assert replay.content == canonical
    assert live.content == canonical


async def test_j2_false_completion_links_claim_to_verified_outcome(tmp_path):
    benchmark_root = tmp_path / "benchmarks"
    ledger = benchmark_root / "j2-probe"
    attempt = ledger / "attempts" / "a1"
    attempt.mkdir(parents=True)
    (ledger / "attempts.jsonl").write_text(
        '{"attempt_id":"a1","journey_id":"J2","status":"complete",'
        '"success":false,"stop_reason":"completed","iterations":90,'
        '"cost_usd":0.21,"result_mode":"full","parse_misses":2,'
        '"wire_sequences":[1,2],"final_state":{"position":{'
        '"title":"Duplicate Entrance","confidence":"ambiguous",'
        '"method":"duplicate-title-not-separated"}}}\n'
    )
    (attempt / "agent.jsonl").write_text(
        '{"phase":"iteration","n":90,"at":"now"}\n'
        '{"phase":"response","at":"now","text":"I am done.",'
        '"cost_usd":0.01,"stop_reason":"end_turn"}\n'
        '{"phase":"turn_end","at":"now","cost_usd":0.21}\n'
    )
    app = create_app(
        Settings(
            gateway_url="http://127.0.0.1:1",
            benchmark_root=benchmark_root,
            web_dist=tmp_path,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        runs = (await client.get("/api/runs")).json()["runs"]
        response = await client.get(
            f"/api/runs/{runs[0]['id']}/investigation"
        )
    payload = response.json()
    findings = {item["kind"]: item for item in payload["diagnostics"]}
    assert findings["false_completion"]["evidence"]
    assert findings["position_ambiguity"]["evidence"]
    assert payload["lens"]["believed"]["text"] == "I am done."
    assert payload["lens"]["truth"]["text"].startswith("Objective not satisfied")
    assert payload["lens"]["parsed"]["text"].startswith("Position: ambiguous")
    assert "{" not in payload["lens"]["parsed"]["text"]
    assert all("/" not in item["label"] for item in payload["citations"])


def test_relative_source_paths_resolve_from_launcher_project_root(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OBSERVATORY_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVATORY_BENCHMARK_ROOT", ".boukensha/benchmarks")
    settings = Settings.from_environment()
    assert settings.benchmark_root == tmp_path / ".boukensha" / "benchmarks"


def test_world_projection_keeps_duplicate_titles_as_distinct_candidates(
    tmp_path,
):
    database = tmp_path / "gateway.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE events ("
        "seq INTEGER PRIMARY KEY, kind TEXT, trace_id TEXT, payload TEXT)"
    )
    rows = [
        (1, "command", "t1", {"line": "north"}),
        (2, "observation", "t1", {
            "kind": "room",
            "title": "White Square",
            "exits": ["south", "east"],
        }),
        (3, "position", "t1", {
            "place": 101,
            "title": "White Square",
            "confidence": "tracked",
            "method": "exits-and-neighbourhood",
        }),
        (4, "command", "t2", {"line": "east"}),
        (5, "observation", "t2", {
            "kind": "room",
            "title": "Nexus",
            "exits": ["west", "north"],
        }),
        (6, "position", "t2", {
            "place": 202,
            "title": "Nexus",
            "confidence": "tracked",
            "method": "exits-and-neighbourhood",
        }),
        (7, "command", "t3", {"line": "north"}),
        (8, "observation", "t3", {
            "kind": "room",
            "title": "White Square",
            "exits": ["south", "west"],
        }),
        (9, "position", "t3", {
            "place": 303,
            "title": "White Square",
            "confidence": "tracked",
            "method": "exits-and-neighbourhood",
        }),
        (10, "parse_metric", "t3", {"cumulative_miss_rate": 0.125}),
        (11, "position", "t4", {
            "place": None,
            "title": "White Square",
            "confidence": "ambiguous",
            "method": "duplicate-title",
        }),
    ]
    connection.executemany(
        "INSERT INTO events VALUES (?, ?, ?, ?)",
        [
            (seq, kind, trace, json.dumps(payload))
            for seq, kind, trace, payload in rows
        ],
    )
    connection.commit()
    connection.close()

    world = project_world(database)

    white_squares = [node for node in world.nodes if node.title == "White Square"]
    assert {node.place for node in white_squares} == {101, 303}
    assert {node.state for node in white_squares} == {"candidate"}
    assert world.candidates == ("place:101", "place:303")
    assert [(edge.source, edge.target, edge.direction) for edge in world.edges] == [
        ("place:101", "place:202", "east"),
        ("place:202", "place:303", "north"),
    ]
    assert world.parse_miss_rate == 0.125
    assert world.unknown_positions == 1


def test_missing_world_database_is_an_honest_empty_projection(tmp_path):
    world = project_world(tmp_path / "missing.db")
    assert world.nodes == ()
    assert world.edges == ()
    assert world.current_confidence == "unknown"


def test_rendering_comparison_aligns_semantics_and_replays_same_results(
    tmp_path,
):
    benchmark_root = tmp_path / "benchmarks"
    paths = {
        "raw": ["look", "move north", "move east", "shop list"],
        "minimal": ["look", "move north", "move south", "shop list"],
        "full": ["look", "move north", "move east", "shop list"],
    }
    for mode, milestones in paths.items():
        ledger = benchmark_root / f"e1-{mode}-n10"
        attempt = ledger / "attempts" / f"{mode}-1"
        attempt.mkdir(parents=True)
        record = {
            "attempt_id": f"{mode}-1",
            "journey_id": "J1",
            "result_mode": mode,
            "success": True,
            "stop_reason": "journey-complete",
            "cost_usd": {"raw": 0.03, "minimal": 0.04, "full": 0.031}[mode],
            "tool_calls": len(milestones),
            "invalid_calls": 0,
            "corrective_calls": 0,
            "tools": {"look": 1, "move": 2, "shop": 1},
            "fresh_input_tokens": 100,
            "cache_read_tokens": 200,
            "cache_write_tokens": 50,
            "output_tokens": 20,
            "tool_result_chars": 500,
            "schema_token_estimate": 1000,
        }
        (ledger / "attempts.jsonl").write_text(json.dumps(record) + "\n")
        events = []
        for milestone in milestones:
            tool, _, argument = milestone.partition(" ")
            key = "direction" if tool == "move" else "action"
            events.append(
                {
                    "phase": "tool_call",
                    "name": f"tbamud__{tool}",
                    "args": {} if not argument else {key: argument},
                }
            )
        if mode == "full":
            events.append(
                {
                    "phase": "tool_result",
                    "result": json.dumps(
                        {
                            "type": "observation",
                            "text": "Bakery menu",
                            "complete": True,
                            "trace_id": "private-metadata",
                        }
                    ),
                }
            )
        (attempt / "agent.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events) + "\n"
        )

    comparison = rendering_comparison(benchmark_root)

    assert comparison is not None
    assert comparison.divergence.index == 3
    assert comparison.divergence.actions == {
        "raw": "move east",
        "minimal": "move south",
        "full": "move east",
    }
    replay = {item.mode: item for item in comparison.counterfactuals}
    assert replay["raw"].bytes < replay["minimal"].bytes < replay["full"].bytes
    assert comparison.cohorts[1].calls_mean == 4


def test_parser_counterfactual_replays_the_exact_recorded_frames(tmp_path):
    from mud_gateway.observe import Coverage, WireReference, parse

    database = tmp_path / "gateway.db"
    raw = (
        b"\x1b[0;33mThe Bakery\x1b[0m\r\n"
        b"\x1b[0;36m[ Exits: west ]\x1b[0m\r\n20H 100M 82V > "
    )
    reference = WireReference.from_bytes("fixture", 7, 7, raw)
    coverage = Coverage()
    coverage.add(parse(raw, reference))
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE events (seq INTEGER PRIMARY KEY, kind TEXT, payload TEXT)"
    )
    connection.execute("CREATE TABLE blobs (digest TEXT PRIMARY KEY, body BLOB)")
    connection.execute(
        "INSERT INTO blobs VALUES (?, ?)",
        (reference.digest, raw),
    )
    connection.execute(
        "INSERT INTO events VALUES (?, ?, ?)",
        (
            8,
            "parse_metric",
            json.dumps(
                {
                    "parser_version": "rules-1",
                    "wire_ref": {
                        "source": "fixture",
                        "first_seq": 7,
                        "last_seq": 7,
                        "digest": reference.digest,
                    },
                    "lines": coverage.lines,
                    "typed": coverage.typed,
                }
            ),
        ),
    )
    connection.commit()
    connection.close()

    replay = replay_parser(database, "full")

    assert replay.frames == 1
    assert replay.typed_delta == 0
    assert replay.recorded_miss_rate == replay.replayed_miss_rate
