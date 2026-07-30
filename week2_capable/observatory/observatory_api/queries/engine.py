"""Plan and dispatch typed, scope-safe Observatory questions."""

from __future__ import annotations

from ..contracts import (
    AskRequest,
    AskResponse,
    ObservatoryQuery,
    QueryScope,
    QueryStep,
)
from ..execution import ExperimentExecutor
from ..sources.benchmark import BenchmarkSource
from ..sources.recorded_session import RecordedSessionSource
from ..sources.runtime import RuntimeSource
from . import experiments as experiment_queries
from . import live as live_queries
from . import recorded as recorded_queries
from .common import missing


def answer(
    request: AskRequest,
    benchmark: BenchmarkSource | None,
    recorded: RecordedSessionSource | None = None,
    runtime: RuntimeSource | None = None,
    experiments: ExperimentExecutor | None = None,
) -> AskResponse:
    """Plan and execute a supported question without arbitrary data access."""

    if request.query is not None and request.query.scope != request.scope:
        return _rejected(
            request,
            request.query,
            "The exact query scope does not match the active workspace scope.",
            "query scope matching the active workspace",
        )
    query = request.query or plan_query(request.question, request.scope)
    if query is None:
        tier = "model_disabled" if request.allow_model else "unsupported"
        return AskResponse(
            tier=tier,
            question=request.question,
            scope_record_id=request.scope.selected_record_id,
            plan=(),
            answer=(
                "No validated local query matches this question. "
                "Model translation is not configured."
                if request.allow_model
                else "No validated local query matches this question."
            ),
            claims=(),
            citations=(),
            missing=("supported query operation",),
        )
    return answer_operation(
        query.operation,
        request,
        benchmark,
        recorded,
        runtime,
        experiments,
        query=query,
    )


def plan_query(question: str, scope: QueryScope) -> ObservatoryQuery | None:
    """Map supported language into a typed, scope-bearing query."""

    operation = plan_operation(question)
    if operation is None:
        normalized = question.casefold()
        if scope.space == "live" and any(
            term in normalized
            for term in ("happening", "current", "doing", "status")
        ):
            operation = "summarize_live"
        elif scope.space == "experiments" and any(
            term in normalized
            for term in ("sample", "job", "definition", "cohort")
        ):
            operation = "list_experiment_samples"
        elif scope.space == "knowledge" and any(
            term in normalized
            for term in ("know", "learn", "fact", "entity", "place")
        ):
            operation = "search_knowledge"
        elif any(
            term in normalized
            for term in ("find", "show", "search", "trace", "record", "room")
        ):
            operation = "search_evidence"
    if operation is None:
        return None
    return ObservatoryQuery(operation=operation, scope=scope)


def plan_operation(question: str) -> str | None:
    """Map supported language to one allowlisted operation."""

    normalized = question.casefold()
    if _contains(normalized, "why", "stop") or _contains(
        normalized, "believe", "complete"
    ):
        return "diagnose_stop"
    if "candidate" in normalized or (
        "position" in normalized
        and ("ambigu" in normalized or "confidence" in normalized)
    ):
        return "list_position_candidates"
    if "compare" in normalized or any(
        mode in normalized for mode in ("raw", "minimal", "full")
    ):
        return "compare_rendering"
    return None


def answer_operation(
    operation: str,
    request: AskRequest,
    benchmark: BenchmarkSource | None,
    recorded: RecordedSessionSource | None = None,
    runtime: RuntimeSource | None = None,
    experiments: ExperimentExecutor | None = None,
    *,
    query: ObservatoryQuery | None = None,
) -> AskResponse:
    """Validate and dispatch one typed evidence operation."""

    selected = query or ObservatoryQuery(
        operation=operation,
        scope=request.scope,
    )
    issue = _scope_issue(selected)
    if issue is not None:
        return _rejected(
            request,
            selected,
            issue,
            "permitted operation for selected space",
        )
    if request.scope.space == "live":
        if operation == "summarize_live":
            result = live_queries.summarize(request, runtime)
        elif operation == "diagnose_stop":
            result = live_queries.diagnose_stop(request, runtime)
        elif operation == "list_position_candidates":
            result = live_queries.position_candidates(request, runtime)
        else:
            result = live_queries.search(request, runtime, selected)
    elif request.scope.space == "sessions":
        if operation == "search_evidence":
            result = recorded_queries.search(request, recorded, selected)
        elif benchmark is None:
            result = _source_missing(request, operation, "selected run")
        elif operation == "diagnose_stop":
            result = recorded_queries.diagnose_stop(
                request,
                benchmark,
                recorded,
            )
        else:
            result = recorded_queries.position_candidates(request, benchmark)
    elif request.scope.space == "experiments":
        if operation == "compare_rendering":
            if benchmark is None:
                result = _source_missing(
                    request,
                    operation,
                    "selected experiment evidence",
                )
            else:
                result = experiment_queries.compare(request, benchmark)
        else:
            result = experiment_queries.samples(
                request,
                benchmark,
                experiments,
                selected,
            )
    else:
        result = missing(
            request,
            QueryStep(
                operation="search_knowledge",
                source="knowledge",
                detail="Search only the selected player's learned state.",
            ),
            "configured per-player knowledge source",
        )
    return _grounded(result).model_copy(update={"query": selected})


def _scope_issue(query: ObservatoryQuery) -> str | None:
    allowed = {
        "live": {
            "diagnose_stop",
            "summarize_live",
            "list_position_candidates",
            "search_evidence",
        },
        "sessions": {
            "diagnose_stop",
            "list_position_candidates",
            "search_evidence",
        },
        "experiments": {
            "compare_rendering",
            "list_experiment_samples",
            "search_evidence",
        },
        "knowledge": {"search_knowledge", "search_evidence"},
    }
    if query.operation not in allowed[query.scope.space]:
        return (
            f"Operation {query.operation} is not permitted in "
            f"{query.scope.space}."
        )
    required = {
        "live": (query.scope.live_session_id, "runtime session"),
        "sessions": (query.scope.run_id, "recorded run"),
        "knowledge": (query.scope.player_id, "player"),
    }
    if query.scope.space in required:
        value, label = required[query.scope.space]
        if not value:
            return f"{query.scope.space.title()} queries require one selected {label}."
    filter_fields = {
        ("live", "search_evidence"): {
            "source",
            "kind",
            "trace_id",
            "cost_usd",
        },
        ("sessions", "search_evidence"): {
            "source",
            "kind",
            "room",
            "trace_id",
            "state",
            "cost_usd",
        },
        ("experiments", "search_evidence"): {
            "arm_id",
            "state",
            "cost_usd",
        },
        ("experiments", "list_experiment_samples"): {
            "arm_id",
            "state",
            "cost_usd",
        },
        ("knowledge", "search_evidence"): {"kind", "confidence"},
    }
    permitted = filter_fields.get(
        (query.scope.space, query.operation),
        set(),
    )
    unsupported = sorted(
        {
            selected.field
            for selected in query.filters
            if selected.field not in permitted
        }
    )
    if unsupported:
        return (
            "Filters are not permitted for this operation: "
            + ", ".join(unsupported)
            + "."
        )
    invalid_operators = sorted(
        {
            f"{selected.field}:{selected.operator}"
            for selected in query.filters
            if (
                selected.field == "cost_usd"
                and selected.operator not in {"eq", "gte", "lte"}
            )
            or (
                selected.field != "cost_usd"
                and selected.operator not in {"eq", "contains"}
            )
        }
    )
    if invalid_operators:
        return (
            "Filter operators are not permitted for these fields: "
            + ", ".join(invalid_operators)
            + "."
        )
    return None


def _rejected(
    request: AskRequest,
    query: ObservatoryQuery,
    detail: str,
    missing_item: str,
) -> AskResponse:
    return AskResponse(
        tier="unsupported",
        question=request.question,
        query=query,
        scope_record_id=request.scope.selected_record_id,
        plan=(
            QueryStep(
                operation="validate_scope",
                source=_scope_source(request.scope.space),
                detail=detail,
            ),
        ),
        answer="The query was rejected before reading evidence.",
        claims=(),
        citations=(),
        missing=(missing_item,),
    )


def _source_missing(
    request: AskRequest,
    operation: str,
    item: str,
) -> AskResponse:
    return missing(
        request,
        QueryStep(
            operation=operation,
            source=_scope_source(request.scope.space),
            detail="Read only the selected scope.",
        ),
        item,
    )


def _grounded(response: AskResponse) -> AskResponse:
    """Keep assertions only when every cited record is returned."""

    available = {citation.id for citation in response.citations}
    supported = tuple(
        claim
        for claim in response.claims
        if claim.citations and set(claim.citations) <= available
    )
    if len(supported) == len(response.claims):
        return response
    return response.model_copy(
        update={
            "claims": supported,
            "missing": (
                *response.missing,
                "returned citations for omitted claims",
            ),
        }
    )


def _scope_source(space: str) -> str:
    return {
        "live": "runtime",
        "sessions": "gateway",
        "experiments": "experiments",
        "knowledge": "knowledge",
    }[space]


def _contains(value: str, *terms: str) -> bool:
    return all(term in value for term in terms)
