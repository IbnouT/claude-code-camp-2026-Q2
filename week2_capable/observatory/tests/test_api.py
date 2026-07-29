from __future__ import annotations

import httpx

from observatory_api.app import create_app
from observatory_api.settings import Settings


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
