"""B9 system evidence, semantic rebuild, and retirement gates."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest

from observatory_v3_backend.api_v1.contracts import (
    ApiError,
    RetiredEndpointResponse,
)
from observatory_v3_backend.app import create_app
from observatory_v3_backend.index import IndexStore
from observatory_v3_backend.repositories.agent import AgentRepository
from observatory_v3_backend.repositories.events import EventRepository
from observatory_v3_backend.retirement import RETIRED_ENDPOINTS
from observatory_v3_backend.settings import Settings
from observatory_v3_backend.sources.gateway import GatewaySource
from observatory_v3_backend.sources.knowledge import KnowledgeSource
from observatory_v3_backend.sources.runtime import RuntimeSource

from .fixtures import build_retained_fixture
from .readiness.fixture import build_readiness_fixture

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
OBSERVATORY_ROOT = PACKAGE_ROOT.parent
READINESS_REPORT = OBSERVATORY_ROOT / "web" / "src" / "dev" / "backend-readiness.json"
RETIREMENT_REPORT = PACKAGE_ROOT / "readiness" / "retired-endpoints.json"


def test_measured_readiness_report_covers_every_system_scenario() -> None:
    report = json.loads(READINESS_REPORT.read_text(encoding="utf-8"))

    assert report["schema"] == "observatory.backend-readiness.v1"
    assert report["environment"]["packages"] == {
        "httpx": "0.28.1",
        "pydantic": "2.13.4",
        "starlette": "1.3.1",
        "uvicorn": "0.52.1",
    }
    assert report["measurement"] == {
        "cache_protocol": "one_excluded_warmup",
        "clock": "time.perf_counter",
        "p50": "median",
        "p95": "nearest_rank",
        "samples": 20,
    }
    assert report["fixture"]["sanitized"] is True
    assert report["fixture"]["sessions"] >= 38
    assert report["fixture"]["gateway_events"] >= 2_000
    assert len(report["fixture"]["digest_sha256"]) == 64
    scenarios = report["scenarios"]
    assert all(
        scenarios[name] is True
        for name in (
            "cold",
            "concurrent",
            "long_session",
            "running_session",
            "stopped_session",
            "warm",
        )
    )
    assert scenarios["restart"]["status_code"] == 200
    assert scenarios["reconnect"]["newest_cursor"] == "cursor-2"
    assert scenarios["reconnect"]["bounded_reconciliation_targets"] <= 64
    for metric in (
        *report["layers"].values(),
        report["resources"]["contract_validation"],
        report["resources"]["event_loop_delay"],
        *report["resources"]["warm"].values(),
    ):
        assert metric["samples"] >= 20
        assert metric["p50_ms"] >= 0
        assert metric["p95_ms"] >= metric["p50_ms"]
    assert report["resources"]["payload_bytes"]["catalog"] < 64 * 1024
    assert report["resources"]["payload_bytes"]["summary"] < 64 * 1024
    assert report["resources"]["payload_bytes"]["live"] < 128 * 1024
    assert all(
        report["resources"]["compressed_payload_bytes"][name]
        <= report["resources"]["payload_bytes"][name]
        for name in ("catalog", "live", "summary")
    )
    assert report["resources"]["concurrent_projection_generation"] == 1
    assert report["resources"]["running_incremental"]["records_added"] == 1
    assert report["resources"]["stopped_session"]["recurring_refresh_requests"] == 0
    assert report["resources"]["partial_line_gap"] is True
    assert report["semantic_reconciliation"]["matched"] is True
    assert report["source_work"]["bootstrap"] == {
        "agent_records": 5_000,
        "gateway_events": 2_000,
        "unrelated_sessions_opened": 0,
    }
    assert report["rebuild"] == {
        "identity_stable": True,
        "resource_id": "session:session-000:summary",
        "source_loss": False,
    }


def test_readiness_fixture_digest_is_reproducible(tmp_path: Path) -> None:
    report = json.loads(READINESS_REPORT.read_text(encoding="utf-8"))
    first = build_readiness_fixture(tmp_path / "first")
    second = build_readiness_fixture(tmp_path / "second")

    assert first.digest == second.digest
    assert first.digest == report["fixture"]["digest_sha256"]


async def test_selected_session_demand_opens_no_unrelated_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=38)
    opened_agent_sessions: list[str] = []
    opened_gateway_sessions: list[str] = []
    original_agent_page = AgentRepository.page
    original_event_page = EventRepository.page

    def agent_page(
        repository: AgentRepository,
        *,
        offset: int = 0,
        start_line: int = 1,
        limit: int = 250,
    ) -> object:
        opened_agent_sessions.append(repository.session.session_id)
        return original_agent_page(
            repository,
            offset=offset,
            start_line=start_line,
            limit=limit,
        )

    def event_page(
        repository: EventRepository,
        *,
        after: int = 0,
        through: int | None = None,
        limit: int = 500,
    ) -> object:
        opened_gateway_sessions.append(repository.session.session_id)
        return original_event_page(
            repository,
            after=after,
            through=through,
            limit=limit,
        )

    monkeypatch.setattr(AgentRepository, "page", agent_page)
    monkeypatch.setattr(EventRepository, "page", event_page)
    application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web",
        )
    )
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            response = await _await_ready(
                client,
                f"/api/v1/sessions/{fixture.selected_session_id}",
            )

    assert response.status_code == 200
    assert set(opened_agent_sessions) == {fixture.selected_session_id}
    assert set(opened_gateway_sessions) == {fixture.selected_session_id}


async def test_disposable_index_rebuild_preserves_semantic_identity(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=3)
    settings = Settings(
        runtime_root=fixture.config_dir,
        web_dist=tmp_path / "web",
    )
    before = await _read_summary(settings, fixture.selected_session_id)
    index_path = fixture.config_dir / "observatory" / "index-v1.sqlite3"
    with IndexStore(index_path) as index:
        index.reset()
    after = await _read_summary(settings, fixture.selected_session_id)

    assert after["resource_id"] == before["resource_id"]
    assert after["source_cursor"] == before["source_cursor"]
    assert after["resource_version"] == before["resource_version"]
    assert after["totals"] == before["totals"]
    assert after["lifecycle"] == before["lifecycle"]


async def test_manifest_routes_are_terminal_bounded_and_typed(
    tmp_path: Path,
) -> None:
    retirement = json.loads(RETIREMENT_REPORT.read_text(encoding="utf-8"))
    manifest = {
        (item["method"], item["legacy"]): item for item in retirement["replacements"]
    }
    runtime = {
        (endpoint.method, endpoint.legacy_path): endpoint
        for endpoint in RETIRED_ENDPOINTS
    }

    assert retirement["schema"] == "observatory.retired-endpoints.v2"
    assert retirement["status"] == "route_retirement_enforced"
    assert len(manifest) == 15
    assert manifest.keys() == runtime.keys()
    assert all(
        item["route_status"] == "retired_typed_410" for item in manifest.values()
    )

    web_dist = tmp_path / "web"
    web_dist.mkdir()
    (web_dist / "index.html").write_text(
        "<main>production observatory</main>",
        encoding="utf-8",
    )
    application = create_app(Settings(web_dist=web_dist))
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            for key, endpoint in runtime.items():
                item = manifest[key]
                response = await client.request(
                    endpoint.method,
                    _concrete_legacy_path(endpoint.legacy_path),
                    json={} if endpoint.method == "POST" else None,
                )
                payload = RetiredEndpointResponse.model_validate(response.json())

                assert response.status_code == 410
                assert response.headers["cache-control"] == "no-store"
                assert response.headers["content-type"] == "application/json"
                assert len(response.content) < 1_024
                assert payload.method == endpoint.method
                assert payload.legacy_path == endpoint.legacy_path
                assert payload.replacements == tuple(item["replacement"])
                if endpoint.legacy_path.endswith(("/events", "/replay")):
                    assert "text/event-stream" not in response.headers["content-type"]
                wrong_method = "POST" if endpoint.method == "GET" else "GET"
                wrong_method_response = await client.request(
                    wrong_method,
                    _concrete_legacy_path(endpoint.legacy_path),
                    json={} if wrong_method == "POST" else None,
                )
                assert 400 <= wrong_method_response.status_code < 600
                assert wrong_method_response.status_code != 410
                assert len(wrong_method_response.content) < 1_024
                assert "text/html" not in wrong_method_response.headers["content-type"]

            for path in (
                "/api/experiments/run",
                "/api/experiments/jobs/job-000/control",
            ):
                response = await client.get(path)
                api_error = ApiError.model_validate(response.json())

                assert response.status_code == 404
                assert response.headers["cache-control"] == "no-store"
                assert response.headers["content-type"] == "application/json"
                assert len(response.content) < 1_024
                assert api_error.error == "not_found"
                assert b"production observatory" not in response.content

            for method, path, expected_status in (
                ("GET", "/api/runs", 200),
                ("GET", "/api/world/atlas", 200),
                ("POST", "/api/experiments/validate", 422),
                ("POST", "/api/players/alpha/knowledge/recovery", 503),
                ("POST", "/api/sessions/session-000/voice", 503),
            ):
                response = await client.request(
                    method,
                    path,
                    json={} if method == "POST" else None,
                )
                assert response.status_code == expected_status
                assert response.status_code != 410


async def test_retired_routes_perform_zero_retained_source_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = build_retained_fixture(fixture_root, session_count=3)
    application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web",
        )
    )
    source_calls: list[str] = []

    def unexpected_sync(*_args: object, **_kwargs: object) -> None:
        source_calls.append("sync")
        raise AssertionError("retired route performed retained source work")

    async def unexpected_async(*_args: object, **_kwargs: object) -> None:
        source_calls.append("async")
        raise AssertionError("retired route performed retained source work")

    async with application.router.lifespan_context(application):
        for owner, methods in (
            (
                RuntimeSource,
                (
                    "sessions",
                    "session",
                    "events",
                    "wire_blob",
                    "agent_events",
                    "operator_messages",
                    "lifecycle",
                    "control",
                ),
            ),
            (KnowledgeSource, ("read",)),
        ):
            for method in methods:
                monkeypatch.setattr(owner, method, unexpected_sync)
        for method in ("sessions", "json", "stream"):
            monkeypatch.setattr(GatewaySource, method, unexpected_async)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            responses = [
                await client.request(
                    endpoint.method,
                    _concrete_legacy_path(endpoint.legacy_path),
                    json={} if endpoint.method == "POST" else None,
                )
                for endpoint in RETIRED_ENDPOINTS
            ]

    assert [response.status_code for response in responses] == [410] * 15
    assert source_calls == []


def test_frontend_consumers_use_only_versioned_replacement_paths() -> None:
    retirement = json.loads(RETIREMENT_REPORT.read_text(encoding="utf-8"))
    operations = {
        (method, path)
        for method, path, _operation in json.loads(
            (PACKAGE_ROOT / "openapi" / "operations.json").read_text(encoding="utf-8")
        )
    }
    replacements = {
        (item["method"], path)
        for item in retirement["replacements"]
        for path in item["replacement"]
    }
    assert replacements <= operations
    api_literal = re.compile(r"""["'`](/api/[^"'`]+)["'`]""")
    consumed: set[str] = set()
    for source in sorted((OBSERVATORY_ROOT / "web" / "src").rglob("*")):
        if source.suffix not in {".ts", ".tsx"} or source.name.endswith(".test.ts"):
            continue
        consumed.update(api_literal.findall(source.read_text(encoding="utf-8")))
    assert consumed
    assert all(path.startswith("/api/v1/") for path in consumed)


def _concrete_legacy_path(template: str) -> str:
    return (
        template.replace("{session}", "session-000")
        .replace("{sequence}", "1")
        .replace("{job_id}", "job-000")
        .replace("{player_id}", "alpha")
    )


async def _read_summary(
    settings: Settings,
    session_id: str,
) -> dict[str, object]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            response = await _await_ready(
                client,
                f"/api/v1/sessions/{session_id}",
            )
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


async def _await_ready(
    client: httpx.AsyncClient,
    path: str,
) -> httpx.Response:
    for _attempt in range(2_000):
        response = await client.get(path)
        if response.status_code != 202:
            return response
        await asyncio.sleep(0)
    raise AssertionError(f"resource did not become ready: {path}")
