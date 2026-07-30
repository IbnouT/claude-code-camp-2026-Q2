from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path

import httpx
from mud_gateway.journal import Event
from mud_gateway.knowledge import EvidenceRef, KnowledgeStore

from observatory_api.app import create_app
from observatory_api.incidents import canonical_payload
from observatory_api.contracts import IncidentCapsule
from observatory_api.projections.parser_replay import replay_parser
from observatory_api.projections.world import project_world, project_world_events
from observatory_api.contracts import QueryScope
from observatory_api.queries import plan_query
from observatory_api.queries.model import ModelTranslator
from observatory_api.redaction import redact_question
from observatory_api.settings import Settings
from observatory_api.execution import ExperimentExecutor
from observatory_api.sources.comparison import (
    rendering_comparison,
    rendering_definition,
)


def test_copilot_query_corpus_routes_only_supported_operations():
    fixture = (
        Path(__file__).parent / "fixtures" / "copilot_queries.json"
    )
    rows = json.loads(fixture.read_text())
    correct = 0
    for row in rows:
        planned = plan_query(
            row["question"],
            QueryScope.model_validate(row["scope"]),
        )
        operation = None if planned is None else planned.operation
        correct += operation == row["operation"]

    report = {
        "operation_accuracy": correct / len(rows),
        "cases": len(rows),
    }
    assert report == {"operation_accuracy": 1.0, "cases": 15}


def test_model_boundary_redacts_secret_shaped_question_text():
    value = redact_question(
        "Why stopped? password=hunter2 token:abc123 "
        "0123456789abcdef0123456789abcdef"
    )
    assert "hunter2" not in value
    assert "abc123" not in value
    assert "0123456789abcdef" not in value
    assert value.count("[REDACTED]") == 3


async def test_optional_model_summary_can_only_cite_returned_evidence():
    async def summarize(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        supplied = json.loads(body["messages"][0]["content"])
        assert supplied["evidence"] == [
            {"id": "gateway:4", "excerpt": "Observed Bakery"}
        ]
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"summary":"The agent observed the Bakery.",'
                            '"citations":["gateway:4"]}'
                        ),
                    }
                ],
                "usage": {"input_tokens": 50, "output_tokens": 12},
            },
        )

    translator = ModelTranslator(
        endpoint="https://example.test/messages",
        api_key="test-token",
        model="pinned-model",
        input_rate=1,
        output_rate=5,
        transport=httpx.MockTransport(summarize),
    )

    result = await translator.summarize(
        question="Where was it?",
        answer="The selected record names the Bakery.",
        claims=(("The room was Bakery.", ("gateway:4",)),),
        citations=(("gateway:4", "Observed Bakery"),),
        missing=(),
    )

    assert result.summary == "The agent observed the Bakery."
    assert result.citations == ("gateway:4",)
    assert result.cost_usd == 0.00011


def test_copilot_policy_loads_from_yaml_while_secret_stays_in_environment(
    tmp_path,
    monkeypatch,
):
    config = tmp_path / ".boukensha"
    config.mkdir()
    (config / "settings.yaml").write_text(
        """
observatory:
  disabled_features:
    - benchmark-execution
  copilot:
    model: pinned-model
    endpoint: https://example.test/messages
    spend_cap_usd: 0.25
    input_rate_per_million: 1.5
    output_rate_per_million: 7.5
""",
        encoding="utf-8",
    )
    (config / ".env").write_text(
        "ANTHROPIC_API_KEY=environment-only-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOUKENSHA_DIR", str(config))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    settings = Settings.from_environment()

    assert settings.copilot_model == "pinned-model"
    assert settings.copilot_endpoint == "https://example.test/messages"
    assert settings.copilot_spend_cap == 0.25
    assert settings.copilot_input_rate == 1.5
    assert settings.copilot_output_rate == 7.5
    assert settings.copilot_api_key == "environment-only-secret"
    assert settings.disabled_features == ("benchmark-execution",)
    assert "environment-only-secret" not in (
        config / "settings.yaml"
    ).read_text(encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY")


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
    assert sources["world"]["state"] == "disabled"


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


async def test_experiment_execution_requires_confirmation_before_policy(tmp_path):
    app = create_app(
        Settings(
            web_dist=tmp_path,
            experiment_execution_enabled=False,
            experiment_max_spend_cap=10,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        unconfirmed = await client.post(
            "/api/experiments/run",
            json={
                "request_id": "test-unconfirmed",
                "definition": rendering_definition().model_dump(mode="json"),
                "player_profile": "poucet",
                "confirmed": False,
                "confirmed_max_spend_usd": 18,
            },
        )
        confirmed_but_disabled = await client.post(
            "/api/experiments/run",
            json={
                "request_id": "test-disabled",
                "definition": rendering_definition().model_dump(mode="json"),
                "player_profile": "poucet",
                "confirmed": True,
                "confirmed_max_spend_usd": 18,
            },
        )
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["error"] == "confirmation_required"
    assert confirmed_but_disabled.status_code == 503
    assert confirmed_but_disabled.json()["error"] == "execution_disabled"


async def test_persisted_experiment_jobs_reopen_without_enabling_execution(
    tmp_path,
):
    benchmark_root = tmp_path / "benchmarks"
    state_root = tmp_path / "experiments"
    definition = rendering_definition().model_copy(
        update={"repetitions_per_arm": 1, "effective_max_spend_usd": 1.8}
    )
    executor = ExperimentExecutor(
        state_root,
        benchmark_root=benchmark_root,
        repository_root=tmp_path,
    )
    executor.create(
        request_id="persisted-job",
        definition=definition,
        player_profile="poucet",
        confirmed_max_spend_usd=1.8,
    )
    app = create_app(
        Settings(
            web_dist=tmp_path,
            benchmark_root=benchmark_root,
            experiment_state_root=state_root,
            experiment_execution_enabled=False,
            experiment_max_spend_cap=10,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/experiments/jobs")

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["id"] == "persisted-job"
    assert jobs[0]["definition"]["id"] == definition.id


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


async def test_world_atlas_reports_an_honest_capability_gap(tmp_path):
    app = create_app(Settings(world_root=None, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/world/atlas")
    assert response.status_code == 200
    assert response.json()["source_state"] == "unavailable"
    assert response.json()["nodes"] == []


async def test_world_atlas_uses_zone_lod_without_collapsing_titles(tmp_path):
    world = tmp_path / "wld"
    world.mkdir()
    (world / "test.wld").write_text(
        "#100\nDuplicate Hall~\nDescription\n~\n7 0 0\n"
        "D0\nNorth~\n~\n0 0 101\nS\n"
        "#101\nDuplicate Hall~\nDescription\n~\n7 0 0\n"
        "D2\nSouth~\n~\n0 0 100\nS\n$\n"
    )
    app = create_app(Settings(world_root=world, web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        overview = (await client.get("/api/world/atlas")).json()
        zone = (
            await client.get("/api/world/atlas?level=zone&zone=7")
        ).json()
    assert overview["room_count"] == 2
    assert overview["duplicate_title_count"] == 1
    assert str(tmp_path) not in overview["source_label"]
    assert overview["zones"][0]["room_count"] == 2
    assert [node["vnum"] for node in zone["nodes"]] == [100, 101]


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
        '"profile_id":"poucet",'
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
                "scope": {
                    "space": "sessions",
                    "run_id": runs[0]["id"],
                },
            },
        )
        translated = await client.post(
            "/api/ask",
            json={
                "question": (
                    "I need an autopsy of the final decision "
                    "token=private-value"
                ),
                "scope": {
                    "space": "sessions",
                    "run_id": runs[0]["id"],
                },
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
        '"profile_id":"poucet",'
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
    runtime_root = tmp_path / ".boukensha"
    knowledge_path = runtime_root / "profiles" / "poucet" / "knowledge.db"
    knowledge_path.parent.mkdir(parents=True)
    knowledge_store = KnowledgeStore(knowledge_path, player_id="poucet")
    knowledge_store.assert_fact(
        "player:poucet",
        "private.note",
        "See /Users/reviewer/private/knowledge.txt token=knowledge-secret",
        layer="learned",
        confidence="high",
        evidence=EvidenceRef(
            session_id="session-private",
            source_seq=1,
            wire_digest="wire-private-1",
            parser_version="rules-1",
            method="test-rule",
            observed_at=1.0,
        ),
    )
    knowledge_store.close()
    app = create_app(
        Settings(
            benchmark_root=benchmark_root,
            runtime_root=runtime_root,
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
        knowledge = await client.get(
            f"/api/runs/{run_id}/knowledge-projection"
        )
        history = await client.get("/api/diagnostic-history")
        exported = await client.post(
            "/api/incidents/export",
            json={
                "run_id": run_id,
                "selected_record_id": "agent:2",
                "diagnostic_id": "false-completion",
                "lens": "diagnostics",
                "annotations": [{
                    "id": "note-1",
                    "target_id": "agent:2",
                    "bookmark": True,
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
    assert "knowledge-secret" not in exported.text
    capsule = IncidentCapsule.model_validate_json(exported.text)
    assert capsule.payload.investigation.run.id == run_id
    assert capsule.version == 2
    assert capsule.payload.player_id == "poucet"
    assert capsule.payload.selection.selected_record_id == "agent:2"
    assert capsule.payload.selection.lens == "diagnostics"
    assert capsule.payload.annotations[0].text.count("[REDACTED]") == 1
    assert "[LOCAL_PATH]" in capsule.payload.annotations[0].text
    assert capsule.payload.source_versions["repository"] == "abc123"
    assert capsule.payload.redaction.replacements >= 2
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


def test_world_source_uses_shared_non_secret_settings(tmp_path, monkeypatch):
    config = tmp_path / ".boukensha"
    world = tmp_path / "world"
    config.mkdir()
    world.mkdir()
    (config / "settings.yaml").write_text(
        "observatory:\n  world:\n    path: world\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOUKENSHA_WORLD", raising=False)
    monkeypatch.delenv("BOUKENSHA_DIR", raising=False)
    assert Settings.from_environment().world_root == world


def test_experiment_policy_uses_shared_non_secret_settings(tmp_path, monkeypatch):
    config = tmp_path / ".boukensha"
    benchmarks = config / "benchmarks"
    config.mkdir()
    benchmarks.mkdir()
    (config / "settings.yaml").write_text(
        "observatory:\n"
        "  benchmark:\n"
        "    path: .boukensha/benchmarks\n"
        "  experiments:\n"
        "    execution_enabled: true\n"
        "    max_spend_cap_usd: 3.5\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OBSERVATORY_BENCHMARK_ROOT", raising=False)
    monkeypatch.delenv("BOUKENSHA_DIR", raising=False)
    settings = Settings.from_environment()
    assert settings.benchmark_root == benchmarks
    assert settings.experiment_execution_enabled is True
    assert settings.experiment_max_spend_cap == 3.5


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
            "mobs": ["Massive Minotaur"],
            "objects": ["silver key"],
        }),
        (9, "position", "t3", {
            "place": 303,
            "title": "White Square",
            "confidence": "tracked",
            "method": "exits-and-neighbourhood",
        }),
        (10, "parse_metric", "t3", {"cumulative_miss_rate": 0.125}),
        (11, "observation", "t4", {
            "kind": "room",
            "title": "White Square",
            "exits": ["south", "west"],
        }),
        (12, "position", "t4", {
            "place": None,
            "title": "White Square",
            "confidence": "ambiguous",
            "method": "duplicate-title",
        }),
        (13, "unparsed", "t4", {
            "reason": "A malformed exit line was retained",
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

    world = project_world(
        database,
        objective="Find and fight the Massive Minotaur",
    )

    white_squares = [node for node in world.nodes if node.title == "White Square"]
    assert {node.place for node in white_squares} == {101, 303}
    assert {node.state for node in white_squares} == {"candidate"}
    assert world.candidates == ("place:101", "place:303")
    details = {item.node_id: item for item in world.candidate_details}
    assert details["place:101"].supporting_exits == ("south",)
    assert details["place:101"].conflicting_exits == ("east", "west")
    assert details["place:303"].supporting_exits == ("south", "west")
    assert details["place:303"].conflicting_exits == ()
    assert world.duplicate_titles[0].node_ids == (
        "place:101",
        "place:303",
    )
    assert [(edge.source, edge.target, edge.direction) for edge in world.edges] == [
        ("place:101", "place:202", "east"),
        ("place:202", "place:303", "north"),
    ]
    assert world.parse_miss_rate == 0.125
    assert world.parse_misses[0].sequence == 13
    assert world.parse_misses[0].reason == "A malformed exit line was retained"
    assert world.unknown_positions == 1
    place_303 = next(node for node in world.nodes if node.place == 303)
    assert place_303.mobs == ("Massive Minotaur",)
    assert place_303.objects == ("silver key",)
    assert world.objective_beacons[0].node_id == "place:303"
    assert world.objective_beacons[0].evidence == (9,)
    replayed = project_world_events(
        (
            Event(
                seq=seq,
                session="session",
                at=float(seq),
                monotonic=float(seq),
                kind=kind,
                trace_id=trace,
                payload=payload,
            )
            for seq, kind, trace, payload in rows
        ),
        objective="Find and fight the Massive Minotaur",
    )
    assert replayed == world


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
    assert len(comparison.samples) == 3
    assert comparison.definition.stop.operator_stop_enabled is True
    assert comparison.registry[0].id == "render.mode"


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
