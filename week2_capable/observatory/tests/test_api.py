from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path

import httpx

from observatory_api.app import create_app
from observatory_api.incidents import canonical_payload
from observatory_api.contracts import IncidentCapsule
from observatory_api.projections.parser_replay import replay_parser
from observatory_api.projections.world import project_world
from observatory_api.queries import plan_operation
from observatory_api.redaction import redact_question
from observatory_api.settings import Settings
from observatory_api.sources.comparison import rendering_comparison


def test_copilot_query_corpus_routes_only_supported_operations():
    fixture = (
        Path(__file__).parent / "fixtures" / "copilot_queries.json"
    )
    for row in json.loads(fixture.read_text()):
        assert plan_operation(row["question"]) == row["operation"]


def test_model_boundary_redacts_secret_shaped_question_text():
    value = redact_question(
        "Why stopped? password=hunter2 token:abc123 "
        "0123456789abcdef0123456789abcdef"
    )
    assert "hunter2" not in value
    assert "abc123" not in value
    assert "0123456789abcdef" not in value
    assert value.count("[REDACTED]") == 3


async def test_health_is_read_only(tmp_path):
    app = create_app(Settings(web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/health")
    assert response.json() == {
        "status": "ok",
        "evidence_plane": "read_only",
        "control_plane": "authenticated_local",
    }


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


async def test_capability_flags_disable_only_named_features(tmp_path):
    app = create_app(
        Settings(
            gateway_url="http://127.0.0.1:1",
            web_dist=tmp_path,
            disabled_features=("compare", "copilot-local"),
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        features = (await client.get("/api/capabilities")).json()["features"]
    assert "compare" not in features
    assert "copilot-local" not in features
    assert "incident-capsules" in features


async def test_corrupt_benchmark_rows_do_not_hide_readable_runs(tmp_path):
    root = tmp_path / "benchmarks"
    ledger = root / "mixed"
    ledger.mkdir(parents=True)
    (ledger / "attempts.jsonl").write_text(
        "not json\n"
        '{"unexpected":"row"}\n'
        '{"attempt_id":"good","journey_id":"J1","success":true,'
        '"stop_reason":"complete","iterations":1,"cost_usd":0.01,'
        '"result_mode":"raw"}\n'
    )
    app = create_app(Settings(benchmark_root=root, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        runs = (await client.get("/api/runs")).json()["runs"]
    assert [run["attempt"] for run in runs] == ["good"]


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
    payload = response.json()
    assert payload["version"] == 1
    assert payload["players"] == [{"id": "legacy", "label": "Legacy gateway"}]
    assert [session["id"] for session in payload["sessions"]] == ["s1", "s2"]


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

    async def translator(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert set(body) == {
            "model",
            "max_tokens",
            "temperature",
            "system",
            "messages",
        }
        question = body["messages"][0]["content"]
        assert "I need an autopsy" in question
        assert "private-value" not in question
        assert "[REDACTED]" in question
        return httpx.Response(
            200,
            json={
                "content": [{
                    "type": "text",
                    "text": '```json\n{"operation":"diagnose_stop"}\n```',
                }],
                "usage": {"input_tokens": 100, "output_tokens": 10},
            },
        )

    app = create_app(
        Settings(
            gateway_url="http://127.0.0.1:1",
            benchmark_root=benchmark_root,
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
        runs = (await client.get("/api/runs")).json()["runs"]
        response = await client.get(
            f"/api/runs/{runs[0]['id']}/investigation"
        )
        asked = await client.post(
            "/api/ask",
            json={
                "question": "Why did the agent stop?",
                "run_id": runs[0]["id"],
            },
        )
        translated = await client.post(
            "/api/ask",
            json={
                "question": (
                    "I need an autopsy of the final decision "
                    "token=private-value"
                ),
                "run_id": runs[0]["id"],
                "allow_model": True,
            },
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
    answer = asked.json()
    assert answer["tier"] == "deterministic"
    assert [step["operation"] for step in answer["plan"]] == [
        "locate_final_claim",
        "verify_objective",
    ]
    assert answer["claims"]
    assert answer["citations"]
    model_answer = translated.json()
    assert model_answer["tier"] == "model_translated"
    assert [step["operation"] for step in model_answer["plan"]] == [
        "locate_final_claim",
        "verify_objective",
    ]
    assert model_answer["model_cost_usd"] > 0


async def test_incident_capsule_is_sanitized_integrity_sealed_and_portable(
    tmp_path,
):
    benchmark_root = tmp_path / "benchmarks"
    ledger = benchmark_root / "j2-portable"
    attempt = ledger / "attempts" / "a1"
    attempt.mkdir(parents=True)
    (ledger / "attempts.jsonl").write_text(
        '{"attempt_id":"a1","journey_id":"J2","status":"complete",'
        '"success":false,"stop_reason":"completed","iterations":2,'
        '"cost_usd":0.02,"result_mode":"full","parse_misses":1,'
        '"final_state":{"position":{"title":"Crossroads",'
        '"confidence":"ambiguous","method":"duplicate-title"}}}\n'
    )
    (attempt / "agent.jsonl").write_text(
        '{"phase":"response","at":"now","text":"I am done.",'
        '"cost_usd":0.01}\n'
        '{"phase":"turn_end","at":"now","cost_usd":0.02}\n'
    )
    app = create_app(
        Settings(
            benchmark_root=benchmark_root,
            web_dist=tmp_path,
            revision="abc123",
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        runs = (await client.get("/api/runs")).json()["runs"]
        run_id = runs[0]["id"]
        knowledge = await client.get(f"/api/runs/{run_id}/knowledge")
        history = await client.get("/api/diagnostic-history")
        exported = await client.post(
            "/api/incidents/export",
            json={
                "run_id": run_id,
                "selected_sequence": 2,
                "diagnostic_id": "false-completion",
                "annotations": [{
                    "id": "note-1",
                    "at": 2,
                    "text": (
                        "Check /Users/reviewer/private/run.json "
                        "token=private-value"
                    ),
                    "created_at": "2026-07-29T00:00:00Z",
                }],
            },
        )

    assert knowledge.status_code == 200
    assert knowledge.json()["missing_layers"] == [
        "entities",
        "player",
        "progression",
        "durable knowledge store",
    ]
    assert history.json()["total_runs"] == 1
    assert history.json()["failed_runs"] == 1
    assert exported.headers["content-type"].startswith(
        "application/vnd.boukensha.incident+json"
    )
    assert "/Users/" not in exported.text
    assert "private-value" not in exported.text
    capsule = IncidentCapsule.model_validate_json(exported.text)
    assert capsule.payload.investigation.run.id == run_id
    assert capsule.payload.selection.selected_sequence == 2
    assert capsule.payload.annotations[0].text.count("[REDACTED]") == 1
    assert "[LOCAL_PATH]" in capsule.payload.annotations[0].text
    assert capsule.payload.source_versions["repository"] == "abc123"
    assert capsule.payload.redaction.replacements == 1
    assert capsule.digest == hashlib.sha256(
        canonical_payload(capsule.payload)
    ).hexdigest()


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
