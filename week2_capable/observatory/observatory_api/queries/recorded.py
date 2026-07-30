"""Scope-safe deterministic questions over one recorded-session prefix."""

from __future__ import annotations

from datetime import UTC, datetime

from ..contracts import (
    AnswerClaim,
    AskRequest,
    AskResponse,
    EvidenceCitation,
    ObservatoryQuery,
    QueryStep,
)
from ..projections.session import project_recorded_session
from ..sources.benchmark import BenchmarkSource
from ..sources.recorded_session import RecordedSessionSource
from .common import missing, search_terms, values_match_filters


def search(
    request: AskRequest,
    recorded: RecordedSessionSource | None,
    query: ObservatoryQuery,
) -> AskResponse:
    """Search only records at or before the selected replay moment."""

    step = QueryStep(
        operation="search_evidence",
        source="gateway",
        detail=(
            "Search sanitized records only inside the selected recorded run "
            "and replay prefix."
        ),
    )
    if recorded is None or request.scope.run_id is None:
        return missing(request, step, "selected recorded run")
    bundle = recorded.load(request.scope.run_id)
    if bundle is None:
        return missing(request, step, "selected recorded run")
    investigation = project_recorded_session(bundle)
    records = list(investigation.records)
    selected_id = request.scope.selected_record_id
    if selected_id is not None:
        selected = next(
            (record for record in records if record.id == selected_id),
            None,
        )
        if selected is None:
            return missing(request, step, "selected replay record")
        records = [
            record
            for record in records
            if (
                record.sequence < selected.sequence
                or (
                    record.sequence == selected.sequence
                    and record.id == selected.id
                )
            )
        ]
    terms = search_terms(request.question)
    matches = [
        record
        for record in records
        if (
            not terms
            or any(
                term
                in (
                    f"{record.source} {record.form} {record.kind} "
                    f"{record.label} {record.preview} {record.trace_id or ''}"
                ).casefold()
                for term in terms
            )
        )
        and values_match_filters(
            {
                "source": record.source,
                "kind": record.kind,
                "room": record.room_id or "",
                "trace_id": record.trace_id or "",
                "state": record.status,
                "cost_usd": record.cost_usd,
            },
            query,
        )
    ]
    if query.order == "chronological":
        matches.sort(key=lambda record: (record.at, record.sequence, record.id))
    elif query.order == "cost_desc":
        matches.sort(
            key=lambda record: (record.cost_usd, record.sequence),
            reverse=True,
        )
    else:
        matches.sort(key=lambda record: (record.sequence, record.id))
    matches = matches[:query.limit]
    citations = tuple(
        EvidenceCitation(
            id=record.id,
            source=record.source,
            label=record.label,
            sequence=record.sequence,
            trace_id=record.trace_id,
            excerpt=record.preview,
        )
        for record in matches
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer=(
            f"{len(matches)} matching records were found in the selected "
            "recorded-session prefix."
        ),
        claims=(),
        citations=citations,
        missing=(("matching records",) if not matches else ()),
    )


def diagnose_stop(
    request: AskRequest,
    benchmark: BenchmarkSource,
    recorded: RecordedSessionSource | None,
) -> AskResponse:
    """Join a linked experiment sample to its own retained outcome."""

    investigation = (
        benchmark.investigation(request.scope.run_id)
        if request.scope.run_id
        else None
    )
    steps = (
        QueryStep(
            operation="locate_final_claim",
            source="agent",
            detail=(
                "Locate the final model claim available at the selected "
                "replay moment."
            ),
        ),
        QueryStep(
            operation="verify_objective",
            source="benchmark",
            detail=(
                "Use the outcome only because this run is an explicitly "
                "linked experiment sample."
            ),
        ),
    )
    if investigation is None:
        return missing(request, steps[0], "selected run")
    if _before_final_response(request, recorded):
        return AskResponse(
            tier="deterministic",
            question=request.question,
            scope_record_id=request.scope.selected_record_id,
            plan=(steps[0],),
            answer=(
                "At the selected replay moment, the run had not yet retained "
                "its final response. A stop diagnosis would use future "
                "evidence, so no stop reason is asserted here."
            ),
            claims=(),
            citations=(),
            missing=("final response at selected moment",),
        )
    finding = next(
        (
            item
            for item in investigation.diagnostics
            if item.kind == "false_completion"
        ),
        None,
    )
    if finding is None:
        return AskResponse(
            tier="deterministic",
            question=request.question,
            plan=steps,
            answer="The selected run has no false-completion diagnostic.",
            claims=(),
            citations=(),
        )
    claims = (
        AnswerClaim(
            text=f"The agent's final account was: {investigation.lens.believed.text}",
            confidence="high",
            citations=investigation.lens.believed.citations,
        ),
        AnswerClaim(
            text=investigation.lens.truth.text,
            confidence="high",
            citations=investigation.lens.truth.citations,
        ),
        AnswerClaim(
            text=finding.mechanism,
            confidence="high",
            citations=finding.evidence,
        ),
    )
    cited_ids = {
        citation
        for claim in claims
        for citation in claim.citations
    }
    citations = tuple(
        item
        for item in investigation.citations
        if item.id in cited_ids
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=steps,
        answer=(
            "This selected record is an experiment sample, so its retained "
            "outcome includes the objective predicate used for that run. The "
            "agent ended its turn, but that linked predicate remained false. "
            "No benchmark result was attached to an unrelated live session."
        ),
        claims=claims,
        citations=citations,
    )


def position_candidates(
    request: AskRequest,
    benchmark: BenchmarkSource,
) -> AskResponse:
    """List distinct unresolved places for the selected recorded run."""

    investigation = (
        benchmark.investigation(request.scope.run_id)
        if request.scope.run_id
        else None
    )
    step = QueryStep(
        operation="list_position_candidates",
        source="gateway",
        detail="List unresolved place identities with exits and visit evidence.",
    )
    if investigation is None:
        return missing(request, step, "selected run")
    nodes = [
        node
        for node in investigation.world.nodes
        if node.id in investigation.world.candidates
    ]
    citations = tuple(
        EvidenceCitation(
            id=f"gateway:place:{node.place}",
            source="gateway",
            label=f"{node.title}, place {node.place}",
            sequence=node.last_seq,
            trace_id=None,
            excerpt=(
                f"exits={','.join(node.exits) or 'unknown'} "
                f"visits={node.visits} method={node.method}"
            ),
        )
        for node in nodes
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        plan=(step,),
        answer=(
            f"{len(nodes)} distinct place identities remain possible. "
            "Their shared title is not used as identity."
        ),
        claims=tuple(
            AnswerClaim(
                text=(
                    f"{node.title}, place {node.place}, remains possible with "
                    f"exits {', '.join(node.exits) or 'unknown'}."
                ),
                confidence="medium",
                citations=(f"gateway:place:{node.place}",),
            )
            for node in nodes
        ),
        citations=citations,
    )


def _before_final_response(
    request: AskRequest,
    recorded: RecordedSessionSource | None,
) -> bool | None:
    if (
        recorded is None
        or request.scope.run_id is None
        or request.scope.selected_record_id is None
    ):
        return None
    bundle = recorded.load(request.scope.run_id)
    if bundle is None:
        return None
    selected_agent = next(
        (
            row
            for line, row in enumerate(bundle.agent_rows, start=1)
            if f"agent:{line}" == request.scope.selected_record_id
        ),
        None,
    )
    selected_gateway = next(
        (
            row
            for row in bundle.gateway_rows
            if f"gateway:{row.sequence}" == request.scope.selected_record_id
        ),
        None,
    )
    final = next(
        (
            row
            for row in reversed(bundle.agent_rows)
            if row.get("phase") == "response"
        ),
        None,
    )
    if request.scope.selected_record_id == "benchmark:outcome":
        return False
    if final is None:
        return None
    selected_at = (
        _timestamp(selected_agent.get("at"))
        if selected_agent is not None
        else datetime.fromtimestamp(selected_gateway.at, UTC)
        if selected_gateway is not None
        else None
    )
    final_at = _timestamp(final.get("at"))
    if selected_at is None or final_at is None:
        return None
    return selected_at < final_at


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
