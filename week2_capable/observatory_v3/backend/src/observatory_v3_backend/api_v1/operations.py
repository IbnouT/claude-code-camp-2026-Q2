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

from ..contracts import (
    AskRequest,
    AskResponse,
    ExperimentRunRequest,
    ObservatoryCapabilities,
)
from ..resources.contracts import (
    CostRangeResponse,
    EntityPageResponse,
    EvidenceRecordResponse,
    ExperimentCatalogPage,
    ExperimentDetailResponse,
    GoalPageResponse,
    KnowledgeDetailPage,
    KnowledgeEvidencePage,
    KnowledgeSummaryResponse,
    LifecyclePageResponse,
    LivePartitionResponse,
    LiveVitalsResponse,
    MapPrefixResponse,
    MaterializationPendingResponse,
    SearchPageResponse,
    SessionSummaryResponse,
    TracePageResponse,
    TurnPageResponse,
    ValueChunkResponse,
    WireBodyResponse,
)
from .contracts import (
    ApiError,
    CommandResponse,
    ExperimentControlRequest,
    ExperimentJobResponse,
    ExperimentJobsResponse,
    HealthResponse,
    LiveViewResponse,
    ResourceNotification,
    SessionCatalogResponse,
    SessionCommandRequest,
    StartCommandRequest,
)

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
    *,
    parameters: tuple[ParameterSpec, ...] = (),
    materialization_pending: bool = False,
) -> OperationSpec:
    pending = (
        (
            ResponseSpec(
                202,
                "Selected-session materialization is pending",
                MaterializationPendingResponse,
            ),
        )
        if materialization_pending
        else ()
    )
    return OperationSpec(
        method="GET",
        path=path,
        operation_id=operation_id,
        handler=handler,
        tags=(tag,),
        request_model=None,
        responses=(
            ResponseSpec(200, "Successful response", response),
            *pending,
            *ERRORS,
        ),
        parameters=parameters,
    )


SESSION_ID = ParameterSpec(
    "session_id",
    "path",
    {"type": "string", "minLength": 1, "maxLength": 200},
    required=True,
)
CURSOR = ParameterSpec(
    "cursor",
    "query",
    {"type": "string", "minLength": 1, "maxLength": 2_048},
)
PAGE_LIMIT_50 = ParameterSpec(
    "limit",
    "query",
    {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
)
PAGE_LIMIT_20 = ParameterSpec(
    "limit",
    "query",
    {"type": "integer", "minimum": 1, "maximum": 20, "default": 20},
)
PAGE_LIMIT_100 = ParameterSpec(
    "limit",
    "query",
    {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
)
CONTENT_OFFSET = ParameterSpec(
    "offset",
    "query",
    {"type": "integer", "minimum": 0, "default": 0},
)
CONTENT_MAX_BYTES = ParameterSpec(
    "max_bytes",
    "query",
    {"type": "integer", "minimum": 1, "maximum": 65_536, "default": 16_384},
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
    OperationSpec(
        method="GET",
        path="/notifications",
        operation_id="getResourceNotifications",
        handler="resource_notifications",
        tags=("notifications",),
        request_model=None,
        responses=(
            ResponseSpec(
                200,
                "Committed bounded resource notifications",
                ResourceNotification,
                media_type="text/event-stream",
            ),
            *ERRORS,
        ),
        parameters=(
            ParameterSpec(
                "session_id",
                "query",
                {"type": "string", "minLength": 1, "maxLength": 200},
            ),
            ParameterSpec(
                "scope",
                "query",
                {"type": "string", "enum": ["catalog"]},
            ),
            ParameterSpec(
                "Last-Event-ID",
                "header",
                {
                    "type": "string",
                    "pattern": "^[0-9a-f]{32}:[0-9]+$",
                },
            ),
        ),
    ),
    _get(
        "/sessions",
        "getSessionCatalog",
        "session_catalog",
        "sessions",
        SessionCatalogResponse,
        parameters=(
            CURSOR,
            PAGE_LIMIT_50,
            ParameterSpec(
                "player_id",
                "query",
                {"type": "string", "minLength": 1, "maxLength": 120},
            ),
        ),
    ),
    OperationSpec(
        method="POST",
        path="/ask",
        operation_id="askEvidence",
        handler="ask",
        tags=("ask",),
        request_model=AskRequest,
        responses=(
            ResponseSpec(200, "Evidence answer", AskResponse),
            ResponseSpec(422, "Request validation failed", ApiError),
        ),
    ),
    OperationSpec(
        method="POST",
        path="/commands/start",
        operation_id="startSession",
        handler="start_command",
        tags=("commands",),
        request_model=StartCommandRequest,
        responses=(
            ResponseSpec(202, "Durable command accepted", CommandResponse),
            ResponseSpec(409, "Idempotency or session conflict", ApiError),
            ResponseSpec(422, "Request validation failed", ApiError),
            ResponseSpec(503, "Command service unavailable", ApiError),
        ),
    ),
    _get(
        "/commands/{command_id:str}",
        "getCommand",
        "command_status",
        "commands",
        CommandResponse,
        parameters=(
            ParameterSpec(
                "command_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 64},
                required=True,
            ),
        ),
    ),
    OperationSpec(
        method="POST",
        path="/sessions/{session_id:str}/commands",
        operation_id="controlSession",
        handler="session_command",
        tags=("commands",),
        request_model=SessionCommandRequest,
        responses=(
            ResponseSpec(202, "Durable command accepted", CommandResponse),
            ResponseSpec(409, "Idempotency or session conflict", ApiError),
            ResponseSpec(422, "Request validation failed", ApiError),
            ResponseSpec(503, "Command service unavailable", ApiError),
        ),
        parameters=(SESSION_ID,),
    ),
    _get(
        "/sessions/{session_id:str}",
        "getSessionSummary",
        "session_summary",
        "sessions",
        SessionSummaryResponse,
        parameters=(SESSION_ID,),
        materialization_pending=True,
    ),
    _get(
        "/sessions/{session_id:str}/goals",
        "getSessionGoals",
        "goals",
        "sessions",
        GoalPageResponse,
        parameters=(SESSION_ID, CURSOR, PAGE_LIMIT_20),
        materialization_pending=True,
    ),
    _get(
        "/sessions/{session_id:str}/goals/{goal_id:str}/turns",
        "getGoalTurns",
        "turns",
        "sessions",
        TurnPageResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "goal_id",
                "path",
                {"type": "string", "minLength": 1},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_20,
        ),
    ),
    _get(
        "/sessions/{session_id:str}/lifecycle",
        "getSessionLifecycle",
        "lifecycle",
        "sessions",
        LifecyclePageResponse,
        parameters=(SESSION_ID, CURSOR, PAGE_LIMIT_100),
    ),
    _get(
        "/sessions/{session_id:str}/lifecycle/{sequence:int}/content",
        "getLifecycleContent",
        "lifecycle_content",
        "sessions",
        ValueChunkResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "sequence",
                "path",
                {"type": "integer", "minimum": 1},
                required=True,
            ),
            CONTENT_OFFSET,
            CONTENT_MAX_BYTES,
        ),
        materialization_pending=True,
    ),
    _get(
        "/sessions/{session_id:str}/turns/{turn_id:str}/iterations",
        "getTurnIterations",
        "iterations",
        "sessions",
        EntityPageResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "turn_id",
                "path",
                {"type": "string", "minLength": 1},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_100,
        ),
    ),
    _get(
        "/sessions/{session_id:str}/evidence/{record_id:str}/children",
        "getEvidenceChildren",
        "evidence_children",
        "evidence",
        EntityPageResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "record_id",
                "path",
                {"type": "string", "minLength": 1},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_100,
        ),
    ),
    _get(
        "/sessions/{session_id:str}/evidence/{record_id:str}",
        "getEvidenceRecord",
        "evidence_record",
        "evidence",
        EvidenceRecordResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "record_id",
                "path",
                {"type": "string", "minLength": 1},
                required=True,
            ),
        ),
        materialization_pending=True,
    ),
    _get(
        "/sessions/{session_id:str}/evidence/{record_id:str}/content",
        "getEvidenceContent",
        "evidence_content",
        "evidence",
        ValueChunkResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "record_id",
                "path",
                {"type": "string", "minLength": 1},
                required=True,
            ),
            CONTENT_OFFSET,
            CONTENT_MAX_BYTES,
        ),
        materialization_pending=True,
    ),
    _get(
        "/sessions/{session_id:str}/traces/{trace_id:str}",
        "getCorrelatedTrace",
        "trace",
        "evidence",
        TracePageResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "trace_id",
                "path",
                {"type": "string", "minLength": 1},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_100,
        ),
    ),
    _get(
        "/sessions/{session_id:str}/wire/{digest:str}",
        "getWireBody",
        "wire_body",
        "evidence",
        WireBodyResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "digest",
                "path",
                {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                required=True,
            ),
            ParameterSpec(
                "max_bytes",
                "query",
                {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 65_536,
                    "default": 16_384,
                },
            ),
        ),
    ),
    _get(
        "/sessions/{session_id:str}/map",
        "getSessionMapPrefix",
        "map_prefix",
        "sessions",
        MapPrefixResponse,
        parameters=(SESSION_ID, CURSOR),
    ),
    _get(
        "/sessions/{session_id:str}/cost",
        "getSessionCostRange",
        "cost_range",
        "sessions",
        CostRangeResponse,
        parameters=(
            SESSION_ID,
            CURSOR,
            PAGE_LIMIT_100,
            ParameterSpec(
                "scope_id",
                "query",
                {"type": "string", "minLength": 1},
            ),
        ),
    ),
    _get(
        "/sessions/{session_id:str}/search",
        "searchSessionEvidence",
        "search",
        "evidence",
        SearchPageResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "q",
                "query",
                {"type": "string", "minLength": 1, "maxLength": 500},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_50,
        ),
    ),
    _get(
        "/live/{session_id:str}/vitals",
        "getLiveVitals",
        "live_vitals",
        "live",
        LiveVitalsResponse,
        parameters=(SESSION_ID,),
    ),
    _get(
        "/live/{session_id:str}/view",
        "getLiveView",
        "live_view",
        "live",
        LiveViewResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "through",
                "query",
                {"type": "integer", "minimum": 1},
            ),
        ),
    ),
    _get(
        "/live/{session_id:str}/{partition:str}",
        "getLivePartition",
        "live_partition",
        "live",
        LivePartitionResponse,
        parameters=(
            SESSION_ID,
            ParameterSpec(
                "partition",
                "path",
                {
                    "type": "string",
                    "enum": [
                        "identity-lifecycle",
                        "world-map",
                        "position-path",
                        "thought-activity",
                        "vitals-combat",
                        "economics",
                        "controls",
                        "diagnostics",
                    ],
                },
                required=True,
            ),
        ),
    ),
    _get(
        "/experiments",
        "getExperimentCatalog",
        "experiment_catalog",
        "experiments",
        ExperimentCatalogPage,
        parameters=(CURSOR, PAGE_LIMIT_50),
    ),
    OperationSpec(
        method="POST",
        path="/experiments/run",
        operation_id="runExperiment",
        handler="run_experiment",
        tags=("experiments",),
        request_model=ExperimentRunRequest,
        responses=(
            ResponseSpec(202, "Durable experiment accepted", ExperimentJobResponse),
            ResponseSpec(409, "Confirmation or idempotency conflict", ApiError),
            ResponseSpec(422, "Experiment validation failed", ApiError),
            ResponseSpec(503, "Experiment execution unavailable", ApiError),
        ),
    ),
    _get(
        "/experiments/jobs",
        "getExperimentJobs",
        "experiment_jobs",
        "experiments",
        ExperimentJobsResponse,
        parameters=(CURSOR, PAGE_LIMIT_50),
    ),
    _get(
        "/experiments/jobs/{job_id:str}",
        "getExperimentJob",
        "experiment_job",
        "experiments",
        ExperimentJobResponse,
        parameters=(
            ParameterSpec(
                "job_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 160},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_100,
        ),
    ),
    OperationSpec(
        method="POST",
        path="/experiments/jobs/{job_id:str}/control",
        operation_id="controlExperiment",
        handler="control_experiment",
        tags=("experiments",),
        request_model=ExperimentControlRequest,
        responses=(
            ResponseSpec(200, "Experiment lifecycle updated", ExperimentJobResponse),
            ResponseSpec(409, "Experiment state conflict", ApiError),
            ResponseSpec(404, "Experiment job not found", ApiError),
            ResponseSpec(422, "Invalid control request", ApiError),
            ResponseSpec(503, "Experiment execution unavailable", ApiError),
        ),
        parameters=(
            ParameterSpec(
                "job_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 160},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_100,
        ),
    ),
    _get(
        "/experiments/{experiment_id:str}",
        "getExperimentDetail",
        "experiment_detail",
        "experiments",
        ExperimentDetailResponse,
        parameters=(
            ParameterSpec(
                "experiment_id",
                "path",
                {"type": "string", "minLength": 1},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_100,
        ),
    ),
    _get(
        "/knowledge/{player_id:str}",
        "getKnowledgeSummary",
        "knowledge_summary",
        "knowledge",
        KnowledgeSummaryResponse,
        parameters=(
            ParameterSpec(
                "player_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 120},
                required=True,
            ),
        ),
    ),
    _get(
        "/knowledge/{player_id:str}/{kind:str}",
        "getKnowledgeDetail",
        "knowledge_detail",
        "knowledge",
        KnowledgeDetailPage,
        parameters=(
            ParameterSpec(
                "player_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 120},
                required=True,
            ),
            ParameterSpec(
                "kind",
                "path",
                {
                    "type": "string",
                    "enum": ["assertion", "change", "snapshot", "recovery"],
                },
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_100,
        ),
    ),
    _get(
        "/knowledge/{player_id:str}/assertions/{assertion_id:str}/evidence",
        "getKnowledgeAssertionEvidence",
        "knowledge_evidence",
        "knowledge",
        KnowledgeEvidencePage,
        parameters=(
            ParameterSpec(
                "player_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 120},
                required=True,
            ),
            ParameterSpec(
                "assertion_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 200},
                required=True,
            ),
            CURSOR,
            PAGE_LIMIT_100,
        ),
    ),
    _get(
        "/knowledge/{player_id:str}/assertions/{assertion_id:str}/content",
        "getKnowledgeAssertionContent",
        "knowledge_assertion_content",
        "knowledge",
        ValueChunkResponse,
        parameters=(
            ParameterSpec(
                "player_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 120},
                required=True,
            ),
            ParameterSpec(
                "assertion_id",
                "path",
                {"type": "string", "minLength": 1, "maxLength": 200},
                required=True,
            ),
            CONTENT_OFFSET,
            CONTENT_MAX_BYTES,
        ),
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
