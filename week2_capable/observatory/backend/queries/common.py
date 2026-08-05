"""Shared primitives for scoped deterministic query handlers."""

from __future__ import annotations

from ..contracts import AskRequest, AskResponse, ObservatoryQuery, QueryStep


def missing(
    request: AskRequest,
    step: QueryStep,
    item: str,
) -> AskResponse:
    """Return one honest capture or configuration gap."""

    return AskResponse(
        tier="deterministic",
        question=request.question,
        scope_record_id=request.scope.selected_record_id,
        plan=(step,),
        answer=f"The query cannot run without {item}.",
        claims=(),
        citations=(),
        missing=(item,),
    )


def search_terms(question: str) -> set[str]:
    """Remove query-language filler while retaining evidence terms."""

    return {
        token
        for token in question.casefold().replace("?", "").split()
        if len(token) > 2
        and token
        not in {
            "find",
            "show",
            "search",
            "the",
            "for",
            "every",
            "record",
            "records",
            "evidence",
        }
    }


def values_match_filters(
    values: dict[str, object],
    query: ObservatoryQuery,
) -> bool:
    """Evaluate only the typed operators admitted by the query contract."""

    for selected in query.filters:
        if selected.field not in values:
            return False
        actual = values[selected.field]
        expected = selected.value
        if selected.operator == "eq" and actual != expected:
            return False
        if (
            selected.operator == "contains"
            and str(expected).casefold() not in str(actual).casefold()
        ):
            return False
        if selected.operator in {"gte", "lte"}:
            try:
                actual_number = float(actual)
                expected_number = float(expected)
            except (TypeError, ValueError):
                return False
            if selected.operator == "gte" and actual_number < expected_number:
                return False
            if selected.operator == "lte" and actual_number > expected_number:
                return False
    return True
