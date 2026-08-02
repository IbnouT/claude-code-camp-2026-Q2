"""Scope-safe deterministic questions over one runtime session prefix."""

from __future__ import annotations

from ..contracts import (
    AnswerClaim,
    AskRequest,
    AskResponse,
    EvidenceCitation,
    LiveJourneySnapshot,
    ObservatoryQuery,
    QueryStep,
)
from ..projections.live import project_live
from ..sources.runtime import RuntimeSession, RuntimeSource, RuntimeSourceError
from .common import missing, search_terms, values_match_filters


def summarize(
    request: AskRequest,
    runtime: RuntimeSource | None,
) -> AskResponse:
    """Summarize the selected live prefix without another evidence source."""

    step = QueryStep(
        operation="summarize_live",
        source="runtime",
        detail="Project the selected runtime session through the selected sequence.",
    )
    session, snapshot, absent = _selection(request, runtime)
    if session is None or snapshot is None:
        return missing(request, step, absent or "selected runtime session")
    citation = _citation(session)
    facts = [
        f"state {snapshot.lifecycle}",
        f"iteration {snapshot.iteration}",
        (
            f"room {snapshot.current_room}"
            if snapshot.current_room
            else "room not captured"
        ),
        f"observed cost ${snapshot.cost_usd:.4f}",
    ]
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer="The selected live prefix reports " + ", ".join(facts) + ".",
        claims=(
            AnswerClaim(
                text=(
                    f"The selected session is {snapshot.lifecycle} at "
                    f"sequence {snapshot.through_sequence}."
                ),
                confidence="high",
                citations=(citation.id,),
            ),
        ),
        citations=(citation,),
        missing=snapshot.capture_gaps,
    )


def diagnose_stop(
    request: AskRequest,
    runtime: RuntimeSource | None,
) -> AskResponse:
    """Report only lifecycle facts retained for the selected session."""

    step = QueryStep(
        operation="diagnose_stop",
        source="runtime",
        detail=(
            "Inspect only the selected runtime session state and retained "
            "events through the selected sequence."
        ),
    )
    session, snapshot, absent = _selection(request, runtime)
    if session is None or snapshot is None:
        return missing(request, step, absent or "selected runtime session")
    citation = _citation(session)
    if session.live:
        answer_text = (
            "The selected agent has not stopped. Its runtime session is "
            f"{session.state} at sequence {snapshot.through_sequence}."
        )
    else:
        answer_text = (
            f"The selected runtime session is {session.state}. The registry "
            "proves that lifecycle state, but no unrelated benchmark outcome "
            "is consulted for its causal reason."
        )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer=answer_text,
        claims=(
            AnswerClaim(
                text=f"Runtime session {session.id} is {session.state}.",
                confidence="high",
                citations=(citation.id,),
            ),
        ),
        citations=(citation,),
        missing=(
            ()
            if session.live
            else ("explicit stop cause in selected runtime evidence",)
        ),
    )


def position_candidates(
    request: AskRequest,
    runtime: RuntimeSource | None,
) -> AskResponse:
    """List unresolved spatial identities from the selected live prefix."""

    step = QueryStep(
        operation="list_position_candidates",
        source="gateway",
        detail="List unresolved place identities from the selected live prefix.",
    )
    _session, snapshot, absent = _selection(request, runtime)
    if snapshot is None:
        return missing(request, step, absent or "selected runtime session")
    nodes = [
        node for node in snapshot.world.nodes if node.id in snapshot.world.candidates
    ]
    citations = tuple(
        EvidenceCitation(
            id=f"gateway:{node.last_seq}",
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
        answer=f"{len(nodes)} live position candidates remain.",
        claims=tuple(
            AnswerClaim(
                text=f"{node.title}, place {node.place}, remains a candidate.",
                confidence="medium",
                citations=(f"gateway:{node.last_seq}",),
            )
            for node in nodes
        ),
        citations=citations,
        missing=(("candidate position evidence",) if not nodes else ()),
    )


def search(
    request: AskRequest,
    runtime: RuntimeSource | None,
    query: ObservatoryQuery,
) -> AskResponse:
    """Search causal labels without crossing the selected runtime prefix."""

    step = QueryStep(
        operation="search_evidence",
        source="runtime",
        detail=("Search sanitized causal labels only inside the selected live prefix."),
    )
    _session, snapshot, absent = _selection(request, runtime)
    if snapshot is None:
        return missing(request, step, absent or "selected runtime session")
    terms = search_terms(request.question)
    matches = [
        item
        for item in snapshot.timeline
        if (
            not terms
            or any(term in f"{item.kind} {item.label}".casefold() for term in terms)
        )
        and values_match_filters(
            {
                "source": item.source,
                "kind": item.kind,
                "trace_id": item.trace_id or "",
                "cost_usd": item.cost_usd,
            },
            query,
        )
    ]
    if query.order == "cost_desc":
        matches.sort(
            key=lambda item: (item.cost_usd, item.sequence),
            reverse=True,
        )
    else:
        matches.sort(key=lambda item: item.sequence)
    matches = matches[: query.limit]
    citations = tuple(
        EvidenceCitation(
            id=item.id,
            source=item.source,
            label=item.label,
            sequence=item.sequence,
            trace_id=item.trace_id,
            excerpt=f"{item.kind} at sequence {item.sequence}",
        )
        for item in matches
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer=(
            f"{len(matches)} matching records were found in the selected live prefix."
        ),
        claims=(),
        citations=citations,
        missing=(("matching records",) if not matches else ()),
    )


def _selection(
    request: AskRequest,
    runtime: RuntimeSource | None,
) -> tuple[
    RuntimeSession | None,
    LiveJourneySnapshot | None,
    str | None,
]:
    session_id = request.scope.live_session_id
    if runtime is None or not runtime.available or session_id is None:
        return None, None, "selected runtime session"
    try:
        session = runtime.session(session_id)
        if session is None:
            return None, None, "selected runtime session"
        if (
            request.scope.player_id is not None
            and session.player_id != request.scope.player_id
        ):
            return None, None, "runtime session matching the selected player"
        snapshot = project_live(
            session,
            runtime.events(
                session.id,
                through=request.scope.through_sequence,
            ),
            runtime.agent_events(session.id),
            through=request.scope.through_sequence,
        )
    except RuntimeSourceError:
        return None, None, "readable runtime session evidence"
    return session, snapshot, None


def _citation(session: RuntimeSession) -> EvidenceCitation:
    return EvidenceCitation(
        id=f"runtime:session:{session.id}",
        source="runtime",
        label=f"{session.character} runtime session",
        sequence=session.latest_seq,
        trace_id=None,
        excerpt=(
            f"state={session.state} capture={session.capture_status} "
            f"events={session.event_count}"
        ),
    )
