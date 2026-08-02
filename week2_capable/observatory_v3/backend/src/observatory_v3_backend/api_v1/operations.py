"""Single typed registry for callable version 1 operations."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from ..contracts import ObservatoryCapabilities
from .contracts import ApiError, HealthResponse

HttpMethod = Literal["GET", "POST"]
ParameterLocation = Literal["path", "query", "header"]


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """One primitive OpenAPI operation parameter."""

    name: str
    location: ParameterLocation
    schema: dict[str, object]
    required: bool = False


@dataclass(frozen=True, slots=True)
class ResponseSpec:
    """One status-specific response contract."""

    status: int
    description: str
    model: type[BaseModel] | None
    media_type: str = "application/json"


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """One callable route and its complete authored transport contract."""

    method: HttpMethod
    path: str
    operation_id: str
    handler: str
    tags: tuple[str, ...]
    request_model: type[BaseModel] | None
    responses: tuple[ResponseSpec, ...]
    parameters: tuple[ParameterSpec, ...] = ()


ERRORS = (
    ResponseSpec(404, "Resource not found", ApiError),
    ResponseSpec(422, "Request validation failed", ApiError),
    ResponseSpec(503, "Required source unavailable", ApiError),
)


def _get(
    path: str,
    operation_id: str,
    handler: str,
    tag: str,
    response: type[BaseModel],
) -> OperationSpec:
    return OperationSpec(
        method="GET",
        path=path,
        operation_id=operation_id,
        handler=handler,
        tags=(tag,),
        request_model=None,
        responses=(ResponseSpec(200, "Successful response", response), *ERRORS),
    )


API_V1_OPERATIONS: tuple[OperationSpec, ...] = (
    _get("/health", "getHealth", "health", "system", HealthResponse),
    _get(
        "/capabilities",
        "getCapabilities",
        "capabilities",
        "system",
        ObservatoryCapabilities,
    ),
)


Handler = Callable[[Request], Awaitable[Response]]


def _forward_headers(response: Response) -> dict[str, str]:
    return {
        name: value
        for name, value in response.headers.items()
        if name.casefold() not in {"content-length", "content-type"}
    }


def _validated_endpoint(
    operation: OperationSpec,
    handler: Handler,
) -> Handler:
    async def endpoint(request: Request) -> Response:
        response = await handler(request)
        response_spec = next(
            (
                candidate
                for candidate in operation.responses
                if candidate.status == response.status_code
            ),
            None,
        )
        if response_spec is None:
            raise RuntimeError(
                f"{operation.operation_id} returned undocumented status "
                f"{response.status_code}"
            )
        if response.media_type != response_spec.media_type:
            raise RuntimeError(
                f"{operation.operation_id} returned {response.media_type!r}, "
                f"expected {response_spec.media_type!r}"
            )
        if isinstance(response, StreamingResponse):
            return response
        if "json" not in response_spec.media_type:
            return response

        body = json.loads(bytes(response.body))
        if response.status_code >= 400:
            source = body if isinstance(body, dict) else {}
            error = ApiError(
                error=str(source.get("error") or "request_failed"),
                detail=(
                    str(source["detail"]) if source.get("detail") is not None else None
                ),
            )
            return JSONResponse(
                error.model_dump(mode="json"),
                status_code=response.status_code,
                headers=_forward_headers(response),
            )
        if response_spec.model is None:
            return response

        validated = response_spec.model.model_validate(body)
        return JSONResponse(
            validated.model_dump(mode="json"),
            status_code=response.status_code,
            headers=_forward_headers(response),
            media_type=response.media_type,
        )

    endpoint.__name__ = operation.operation_id
    return endpoint


def api_v1_routes(handlers: Mapping[str, Handler]) -> list[Route]:
    """Build callable Starlette routes from the canonical registry."""

    return [
        Route(
            f"/api/v1{operation.path}",
            _validated_endpoint(operation, handlers[operation.handler]),
            methods=[operation.method],
            name=operation.operation_id,
        )
        for operation in API_V1_OPERATIONS
    ]
