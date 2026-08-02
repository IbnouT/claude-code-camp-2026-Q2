"""Scope-safe deterministic search over one player's durable knowledge."""

from __future__ import annotations

import json

from ..contracts import (
    AskRequest,
    AskResponse,
    EvidenceCitation,
    ObservatoryQuery,
    QueryStep,
)
from ..sources.knowledge import KnowledgeSource, KnowledgeSourceError
from .common import missing, search_terms, values_match_filters


def search(
    request: AskRequest,
    source: KnowledgeSource | None,
    query: ObservatoryQuery,
) -> AskResponse:
    """Search assertions and return their exact supporting observations."""

    step = QueryStep(
        operation="search_knowledge",
        source="knowledge",
        detail=(
            "Search only the selected player's durable assertions and "
            "supporting observations."
        ),
    )
    player_id = request.scope.player_id
    if source is None or player_id is None:
        return missing(request, step, "selected player's knowledge source")
    try:
        knowledge = source.read(player_id)
    except KnowledgeSourceError:
        return missing(request, step, "readable selected-player knowledge")
    if knowledge.state != "ready":
        return missing(request, step, "selected player's retained knowledge")

    terms = search_terms(request.question)
    assertions = [
        assertion
        for assertion in knowledge.assertions
        if (
            not terms
            or any(
                term
                in (
                    f"{assertion.subject} {assertion.predicate} "
                    f"{_value(assertion.value)} {assertion.status} "
                    f"{assertion.confidence}"
                ).casefold()
                for term in terms
            )
        )
        and values_match_filters(
            {
                "kind": assertion.predicate,
                "confidence": assertion.confidence,
            },
            query,
        )
    ][: query.limit]
    citations = tuple(
        EvidenceCitation(
            id=f"knowledge:{assertion.assertion_id}",
            source="knowledge",
            label=f"{assertion.subject} · {assertion.predicate}",
            sequence=(assertion.evidence[0].source_seq if assertion.evidence else None),
            trace_id=None,
            excerpt=_value(assertion.value),
        )
        for assertion in assertions
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer=(
            f"{len(assertions)} matching assertions were found in "
            f"{player_id}'s durable knowledge."
        ),
        claims=(),
        citations=citations,
        missing=(
            (*knowledge.capture_gaps, "matching assertions")
            if not assertions
            else knowledge.capture_gaps
        ),
    )


def _value(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
