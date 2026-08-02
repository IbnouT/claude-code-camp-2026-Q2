"""Deterministic questions over universal runtime session evidence."""

from __future__ import annotations

from datetime import datetime

from ..contracts import (
    AnswerClaim,
    AskRequest,
    AskResponse,
    EvidenceCitation,
    ObservatoryQuery,
    QueryStep,
    RuntimeSessionInvestigation,
    SessionEvidenceRecord,
)
from ..projections.runtime_session import project_runtime_session
from ..sources.runtime import RuntimeSession, RuntimeSource, RuntimeSourceError
from .common import missing, search_terms, values_match_filters


def search(
    request: AskRequest,
    runtime: RuntimeSource | None,
    query: ObservatoryQuery,
) -> AskResponse | None:
    """Search one runtime session without crossing an explicit record prefix."""

    step = QueryStep(
        operation="search_evidence",
        source="runtime",
        detail=(
            "Search retained agent and gateway records inside the selected "
            "runtime session."
        ),
    )
    loaded = _load(request, runtime)
    if loaded is None:
        return None
    _session, investigation = loaded
    records, absent = _selected_records(
        investigation.records,
        request.scope.selected_record_id,
    )
    if absent is not None:
        return missing(request, step, absent)
    terms = search_terms(request.question)
    matches = [
        record
        for record in records
        if (not terms or any(term in _searchable_text(record) for term in terms))
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
    matches = matches[: query.limit]
    citations = tuple(_record_citation(record) for record in matches)
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer=(
            f"{len(matches)} matching records were found in the selected session scope."
        ),
        claims=(),
        citations=citations,
        missing=(("matching records",) if not matches else ()),
    )


def diagnose_stop(
    request: AskRequest,
    runtime: RuntimeSource | None,
) -> AskResponse | None:
    """Explain only the lifecycle cause retained by the runtime session."""

    step = QueryStep(
        operation="diagnose_stop",
        source="runtime",
        detail=(
            "Inspect the selected session lifecycle and its retained stop "
            "mode without consulting an unrelated experiment outcome."
        ),
    )
    loaded = _load(request, runtime)
    if loaded is None:
        return None
    session, investigation = loaded
    records, absent = _selected_records(
        investigation.records,
        request.scope.selected_record_id,
    )
    if absent is not None:
        return missing(request, step, absent)
    if (
        request.scope.selected_record_id is not None
        and session.ended_at is not None
        and records
        and _before(records[-1].at, session.ended_at)
    ):
        selected = records[-1]
        citation = _record_citation(selected)
        return AskResponse(
            tier="deterministic",
            question=request.question,
            scope_record_id=request.scope.selected_record_id,
            plan=(step,),
            answer=(
                "At the selected evidence point, the session had not yet "
                "retained its terminal lifecycle state. Explaining the later "
                "stop would cross the selected boundary."
            ),
            claims=(),
            citations=(citation,),
            missing=("terminal lifecycle state at selected evidence",),
        )
    citation = _session_citation(session)
    answer, missing_facts = _stop_answer(session)
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer=answer,
        claims=(
            AnswerClaim(
                text=_stop_claim(session),
                confidence="high",
                citations=(citation.id,),
            ),
        ),
        citations=(citation,),
        missing=missing_facts,
    )


def position_candidates(
    request: AskRequest,
    runtime: RuntimeSource | None,
) -> AskResponse | None:
    """List unresolved place identities from one runtime session."""

    step = QueryStep(
        operation="list_position_candidates",
        source="gateway",
        detail=("List unresolved place identities from the selected runtime session."),
    )
    loaded = _load(request, runtime)
    if loaded is None:
        return None
    _session, investigation = loaded
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
                f"confidence={node.confidence} method={node.method} "
                f"exits={','.join(node.exits) or 'unknown'}"
            ),
        )
        for node in nodes
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer=f"{len(nodes)} session position candidates remain.",
        claims=tuple(
            AnswerClaim(
                text=f"{node.title}, place {node.place}, remains a candidate.",
                confidence="medium",
                citations=(f"gateway:place:{node.place}",),
            )
            for node in nodes
        ),
        citations=citations,
        missing=(("candidate position evidence",) if not nodes else ()),
    )


def _load(
    request: AskRequest,
    runtime: RuntimeSource | None,
) -> tuple[RuntimeSession, RuntimeSessionInvestigation] | None:
    session_id = request.scope.run_id
    if runtime is None or not runtime.available or session_id is None:
        return None
    try:
        session = runtime.session(session_id)
        if session is None:
            return None
        if (
            request.scope.player_id is not None
            and request.scope.player_id != session.player_id
        ):
            return None
        investigation = project_runtime_session(
            session,
            runtime.events(session.id),
            runtime.agent_events(session.id),
            operator_messages=runtime.operator_messages(session.id),
        )
    except RuntimeSourceError:
        return None
    return session, investigation


def _selected_records(
    records: tuple[SessionEvidenceRecord, ...],
    selected_id: str | None,
) -> tuple[list[SessionEvidenceRecord], str | None]:
    selected_records = list(records)
    if selected_id is None:
        return selected_records, None
    selected_index = next(
        (
            index
            for index, record in enumerate(selected_records)
            if record.id == selected_id
        ),
        None,
    )
    if selected_index is None:
        return [], "selected session record"
    return selected_records[: selected_index + 1], None


def _searchable_text(record: SessionEvidenceRecord) -> str:
    return (
        f"{record.source} {record.form} {record.kind} {record.label} "
        f"{record.preview} {record.trace_id or ''} {record.fields}"
    ).casefold()


def _record_citation(record: SessionEvidenceRecord) -> EvidenceCitation:
    return EvidenceCitation(
        id=record.id,
        source=record.source,
        label=record.label,
        sequence=record.sequence,
        trace_id=record.trace_id,
        excerpt=record.preview,
    )


def _session_citation(session: RuntimeSession) -> EvidenceCitation:
    stop_mode = session.stop_mode or "not retained"
    return EvidenceCitation(
        id=f"runtime:session:{session.id}",
        source="runtime",
        label=f"{session.character} session lifecycle",
        sequence=session.latest_seq,
        trace_id=None,
        excerpt=f"state={session.state} stop_mode={stop_mode}",
    )


def _stop_answer(session: RuntimeSession) -> tuple[str, tuple[str, ...]]:
    if session.live:
        return (
            f"This session has not stopped. Its retained lifecycle state is "
            f"{session.state}.",
            (),
        )
    if session.stop_mode == "cooperative":
        return (
            "The session stopped cooperatively. The launcher retained an "
            "operator-requested cooperative stop as its terminal mode.",
            (),
        )
    if session.stop_mode:
        return (
            f"The session ended with lifecycle state {session.state} and "
            f"retained stop mode {session.stop_mode}.",
            (),
        )
    return (
        f"The session ended with lifecycle state {session.state}. No more "
        "specific stop mode was retained, so a deeper cause cannot be "
        "asserted from this session.",
        ("specific stop mode",),
    )


def _stop_claim(session: RuntimeSession) -> str:
    if session.stop_mode:
        return (
            f"Runtime session {session.id} is {session.state} with stop mode "
            f"{session.stop_mode}."
        )
    return f"Runtime session {session.id} is {session.state}."


def _before(left: str, right: str) -> bool:
    try:
        return datetime.fromisoformat(left.replace("Z", "+00:00")) < (
            datetime.fromisoformat(right.replace("Z", "+00:00"))
        )
    except ValueError:
        return False
