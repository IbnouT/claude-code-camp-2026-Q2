"""Terminal responses for legacy HTTP routes replaced by version 1 resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .api_v1.contracts import ApiError, RetiredEndpointResponse

HttpMethod = Literal["GET", "POST"]
LEGACY_API_METHODS = (
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
)


@dataclass(frozen=True, slots=True)
class RetiredEndpoint:
    """One legacy method and path with callable version 1 replacements."""

    method: HttpMethod
    route_path: str
    legacy_path: str
    replacements: tuple[str, ...]


RETIRED_ENDPOINTS = (
    RetiredEndpoint("GET", "/api/health", "/api/health", ("/api/v1/health",)),
    RetiredEndpoint(
        "GET",
        "/api/capabilities",
        "/api/capabilities",
        ("/api/v1/capabilities",),
    ),
    RetiredEndpoint(
        "GET",
        "/api/sessions",
        "/api/sessions",
        ("/api/v1/sessions",),
    ),
    RetiredEndpoint(
        "GET",
        "/api/sessions/{session:str}/snapshot",
        "/api/sessions/{session}/snapshot",
        ("/api/v1/live/{session_id}/{partition}",),
    ),
    RetiredEndpoint(
        "GET",
        "/api/sessions/{session:str}/investigation",
        "/api/sessions/{session}/investigation",
        (
            "/api/v1/sessions/{session_id}",
            "/api/v1/sessions/{session_id}/goals",
            "/api/v1/sessions/{session_id}/search",
        ),
    ),
    RetiredEndpoint(
        "GET",
        "/api/sessions/{session:str}/wire/{sequence:int}",
        "/api/sessions/{session}/wire/{sequence}",
        ("/api/v1/sessions/{session_id}/wire/{digest}",),
    ),
    RetiredEndpoint(
        "POST",
        "/api/sessions/{session:str}/control",
        "/api/sessions/{session}/control",
        ("/api/v1/sessions/{session_id}/commands",),
    ),
    RetiredEndpoint(
        "GET",
        "/api/sessions/{session:str}/events",
        "/api/sessions/{session}/events",
        (
            "/api/v1/notifications",
            "/api/v1/live/{session_id}/{partition}",
        ),
    ),
    RetiredEndpoint(
        "GET",
        "/api/sessions/{session:str}/replay",
        "/api/sessions/{session}/replay",
        (
            "/api/v1/notifications",
            "/api/v1/live/{session_id}/{partition}",
        ),
    ),
    RetiredEndpoint(
        "GET",
        "/api/experiments/catalog",
        "/api/experiments/catalog",
        ("/api/v1/experiments",),
    ),
    RetiredEndpoint(
        "POST",
        "/api/experiments/run",
        "/api/experiments/run",
        ("/api/v1/experiments/run",),
    ),
    RetiredEndpoint(
        "GET",
        "/api/experiments/jobs",
        "/api/experiments/jobs",
        ("/api/v1/experiments/jobs",),
    ),
    RetiredEndpoint(
        "GET",
        "/api/experiments/jobs/{job_id:str}",
        "/api/experiments/jobs/{job_id}",
        ("/api/v1/experiments/jobs/{job_id}",),
    ),
    RetiredEndpoint(
        "POST",
        "/api/experiments/jobs/{job_id:str}/control",
        "/api/experiments/jobs/{job_id}/control",
        ("/api/v1/experiments/jobs/{job_id}/control",),
    ),
    RetiredEndpoint(
        "GET",
        "/api/players/{player_id:str}/knowledge",
        "/api/players/{player_id}/knowledge",
        ("/api/v1/knowledge/{player_id}",),
    ),
)


def retired_endpoint_routes() -> tuple[Route, ...]:
    """Return terminal routes ordered ahead of compatibility fallbacks."""
    return tuple(_retired_route(endpoint) for endpoint in RETIRED_ENDPOINTS)


def unowned_legacy_api_routes() -> tuple[Route, ...]:
    """Return terminal fallbacks ordered after owned compatibility routes."""

    async def not_found(_request: Request) -> JSONResponse:
        response = ApiError(
            error="not_found",
            detail="No unversioned API route owns this method and path.",
        )
        return JSONResponse(
            response.model_dump(mode="json"),
            status_code=404,
            headers={"cache-control": "no-store"},
        )

    return (
        Route(
            "/api",
            not_found,
            methods=list(LEGACY_API_METHODS),
            name="unowned-legacy-api-root",
        ),
        Route(
            "/api/{path:path}",
            not_found,
            methods=list(LEGACY_API_METHODS),
            name="unowned-legacy-api",
        ),
    )


def _retired_route(endpoint: RetiredEndpoint) -> Route:
    async def retired(_request: Request) -> JSONResponse:
        response = RetiredEndpointResponse(
            method=endpoint.method,
            legacy_path=endpoint.legacy_path,
            replacements=endpoint.replacements,
        )
        return JSONResponse(
            response.model_dump(mode="json"),
            status_code=410,
            headers={"cache-control": "no-store"},
        )

    return Route(
        endpoint.route_path,
        retired,
        methods=[endpoint.method],
        name=f"retired:{endpoint.method}:{endpoint.legacy_path}",
    )
