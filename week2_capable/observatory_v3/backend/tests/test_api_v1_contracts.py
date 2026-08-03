"""Contract publication, routing, and fixture parity gates."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from openapi_spec_validator import validate
from starlette.routing import Route

from observatory_v3_backend.api_v1.contracts import SessionCatalogResponse
from observatory_v3_backend.api_v1.openapi import (
    canonical_openapi_json,
    canonical_operations_json,
    openapi_document,
)
from observatory_v3_backend.api_v1.operations import API_V1_OPERATIONS
from observatory_v3_backend.app import create_app
from observatory_v3_backend.settings import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONVERTER = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*):[^}]+}")


def _published_path(path: str) -> str:
    return f"/api/v1{CONVERTER.sub(lambda match: f'{{{match.group(1)}}}', path)}"


def test_openapi_document_is_valid_deterministic_and_current() -> None:
    document = openapi_document()
    validate(document)

    artifact = BACKEND_ROOT / "openapi" / "observatory-v1.json"
    assert artifact.read_text(encoding="utf-8") == canonical_openapi_json()
    assert canonical_openapi_json() == canonical_openapi_json()
    assert document["openapi"] == "3.1.1"


def test_operation_registry_and_openapi_paths_match_exactly() -> None:
    registry = {
        (operation.method.casefold(), _published_path(operation.path))
        for operation in API_V1_OPERATIONS
    }
    paths = openapi_document()["paths"]
    assert isinstance(paths, dict)
    published = {
        (method, path)
        for path, path_item in paths.items()
        if isinstance(path_item, dict)
        for method in path_item
    }

    assert published == registry
    assert len({operation.operation_id for operation in API_V1_OPERATIONS}) == len(
        API_V1_OPERATIONS
    )

    manifest = json.loads(
        (BACKEND_ROOT / "openapi" / "operations.json").read_text(encoding="utf-8")
    )
    assert (BACKEND_ROOT / "openapi" / "operations.json").read_text(
        encoding="utf-8"
    ) == canonical_operations_json()
    expected = {
        (method.casefold(), path, operation_id)
        for method, path, operation_id in manifest
    }
    authored = {
        (
            operation.method.casefold(),
            _published_path(operation.path),
            operation.operation_id,
        )
        for operation in API_V1_OPERATIONS
    }
    assert authored == expected


def test_public_schema_excludes_legacy_complete_investigations() -> None:
    document = openapi_document()
    paths = document["paths"]
    assert isinstance(paths, dict)
    assert {
        "/api/v1/health",
        "/api/v1/capabilities",
        "/api/v1/notifications",
        "/api/v1/sessions",
        "/api/v1/sessions/{session_id}",
        "/api/v1/live/{session_id}/{partition}",
        "/api/v1/experiments",
        "/api/v1/knowledge/{player_id}",
    } <= set(paths)

    components = document["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    assert {
        "ApiError",
        "CommandResponse",
        "ResourceChangedNotification",
        "ResourceChangeTarget",
        "ResourceNotification",
        "ResourceReconciliationNotification",
        "SessionCommandRequest",
        "SessionCatalogResponse",
        "StartCommandRequest",
    } <= set(schemas)
    assert {
        "Investigation",
        "RecordedSessionInvestigation",
        "RuntimeSessionInvestigation",
    }.isdisjoint(schemas)


def test_notification_operation_freezes_statuses_and_typed_stream_models() -> None:
    document = openapi_document()
    paths = document["paths"]
    assert isinstance(paths, dict)
    operation = paths["/api/v1/notifications"]["get"]
    assert isinstance(operation, dict)
    responses = operation["responses"]
    assert isinstance(responses, dict)

    assert set(responses) == {"200", "404", "422", "503"}
    assert responses["200"]["content"]["text/event-stream"]["schema"] == {
        "$ref": "#/components/schemas/ResourceNotification"
    }
    for status in ("404", "422", "503"):
        assert responses[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ApiError"
        }

    components = document["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    assert {
        "ResourceChangeTarget",
        "ResourceNotification",
        "ResourceReconciliationNotification",
    } <= set(schemas)


def test_starlette_routes_derive_from_the_operation_registry(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(web_dist=tmp_path))
    expected = {
        (
            operation.operation_id,
            f"/api/v1{operation.path}",
            operation.method,
        )
        for operation in API_V1_OPERATIONS
    }
    actual = {
        (
            route.name,
            route.path,
            operation.method,
        )
        for operation in API_V1_OPERATIONS
        for route in app.routes
        if isinstance(route, Route)
        if route.name == operation.operation_id
        and operation.method in (route.methods or ())
    }

    assert actual == expected


def test_sanitized_session_fixture_matches_authored_contract() -> None:
    fixture = BACKEND_ROOT / "openapi" / "fixtures" / "session-catalog.json"
    value = SessionCatalogResponse.model_validate_json(
        fixture.read_text(encoding="utf-8")
    )

    assert value.sessions[0].goal_count == 2
    assert value.sessions[0].nudge_count == 1
    assert "token" not in json.dumps(value.model_dump(mode="json")).casefold()


async def test_v1_health_and_unknown_versions_precede_spa_fallback(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        health = await client.get("/api/v1/health")
        prior = await client.get("/api/v0/sessions")
        future = await client.get("/api/v2/sessions")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "evidence_plane": "read_only",
        "control_plane": "authenticated_local",
    }
    for response in (prior, future):
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["contract_version"] == "v1"
        assert response.json()["error"] == "unsupported_api_version"


async def test_bounded_resources_report_unavailable_without_runtime(
    tmp_path: Path,
) -> None:
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
        capabilities = await client.get("/api/v1/capabilities")
        unpublished = await client.get("/api/v1/sessions")

    assert capabilities.status_code == 200
    assert unpublished.status_code == 503
    assert unpublished.json() == {
        "contract_version": "v1",
        "error": "source_unavailable",
        "detail": "The retained session index is not configured.",
    }


async def test_compatibility_health_contract_remains_unchanged(
    tmp_path: Path,
) -> None:
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
