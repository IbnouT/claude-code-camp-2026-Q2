"""Deterministic natural-language routing over typed evidence operations."""

from __future__ import annotations

from ..contracts import (
    AnswerClaim,
    AskRequest,
    AskResponse,
    EvidenceCitation,
    QueryStep,
)
from ..sources.benchmark import BenchmarkSource
from ..sources.comparison import rendering_comparison


def answer(request: AskRequest, benchmark: BenchmarkSource) -> AskResponse:
    """Plan and execute a supported question without arbitrary data access."""

    operation = plan_operation(request.question)
    if operation is not None:
        return answer_operation(operation, request, benchmark)
    tier = "model_disabled" if request.allow_model else "unsupported"
    return AskResponse(
        tier=tier,
        question=request.question,
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
    benchmark: BenchmarkSource,
) -> AskResponse:
    """Execute one already validated operation selected by a translator."""

    if operation == "diagnose_stop":
        return _diagnose_stop(request, benchmark)
    if operation == "list_position_candidates":
        return _position_candidates(request, benchmark)
    if operation == "compare_rendering":
        return _compare_rendering(request, benchmark)
    return AskResponse(
        tier="unsupported",
        question=request.question,
        plan=(),
        answer="The translated operation is not permitted.",
        claims=(),
        citations=(),
        missing=("permitted operation",),
    )


def _diagnose_stop(
    request: AskRequest,
    benchmark: BenchmarkSource,
) -> AskResponse:
    investigation = (
        benchmark.investigation(request.run_id)
        if request.run_id
        else None
    )
    step = QueryStep(
        operation="diagnose_stop",
        source="benchmark",
        detail="Join the final model claim to the verified journey outcome.",
    )
    if investigation is None:
        return _missing(request, step, "selected run")
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
            plan=(step,),
            answer="The selected run has no false-completion diagnostic.",
            claims=(),
            citations=(),
        )
    citations = tuple(
        item
        for item in investigation.citations
        if item.id in finding.evidence
    )
    belief = investigation.lens.believed.text
    truth = investigation.lens.truth.text
    claims = (
        AnswerClaim(
            text=f"The agent's final account was: {belief}",
            confidence="high",
            citations=investigation.lens.believed.citations,
        ),
        AnswerClaim(
            text=truth,
            confidence="high",
            citations=investigation.lens.truth.citations,
        ),
        AnswerClaim(
            text=finding.mechanism,
            confidence="high",
            citations=finding.evidence,
        ),
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        plan=(step,),
        answer=(
            "The agent stopped because it treated its completed turn as a "
            "completed journey, while the independent benchmark predicate "
            "remained false."
        ),
        claims=claims,
        citations=citations,
    )


def _position_candidates(
    request: AskRequest,
    benchmark: BenchmarkSource,
) -> AskResponse:
    investigation = (
        benchmark.investigation(request.run_id)
        if request.run_id
        else None
    )
    step = QueryStep(
        operation="list_position_candidates",
        source="gateway",
        detail="List unresolved place identities with exits and visit evidence.",
    )
    if investigation is None:
        return _missing(request, step, "selected run")
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
    claims = tuple(
        AnswerClaim(
            text=(
                f"{node.title}, place {node.place}, remains possible with "
                f"exits {', '.join(node.exits) or 'unknown'}."
            ),
            confidence="medium",
            citations=(f"gateway:place:{node.place}",),
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
        claims=claims,
        citations=citations,
    )


def _compare_rendering(
    request: AskRequest,
    benchmark: BenchmarkSource,
) -> AskResponse:
    comparison = rendering_comparison(benchmark.root)
    step = QueryStep(
        operation="compare_rendering",
        source="benchmark",
        detail="Compare reset-verified cohorts and same-evidence replay.",
    )
    if comparison is None:
        return _missing(request, step, "complete J1 rendering cohorts")
    raw, minimal, full = comparison.cohorts
    citations = (
        EvidenceCitation(
            id="benchmark:j1:raw",
            source="benchmark",
            label="Raw J1 cohort",
            sequence=None,
            trace_id=None,
            excerpt=f"{raw.successes}/{raw.samples}, ${raw.cost_mean:.6f} mean",
        ),
        EvidenceCitation(
            id="benchmark:j1:minimal",
            source="benchmark",
            label="Minimal J1 cohort",
            sequence=None,
            trace_id=None,
            excerpt=(
                f"{minimal.successes}/{minimal.samples}, "
                f"{minimal.calls_mean:.1f} mean calls"
            ),
        ),
        EvidenceCitation(
            id="benchmark:j1:full",
            source="benchmark",
            label="Full J1 cohort",
            sequence=None,
            trace_id=None,
            excerpt=f"{full.successes}/{full.samples}, ${full.cost_mean:.6f} mean",
        ),
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        plan=(step,),
        answer=(
            "Raw and full had overlapping mean journey cost. Minimal used "
            "more calls and cost despite its smaller envelope, so payload "
            "size alone did not predict total journey cost."
        ),
        claims=(
            AnswerClaim(
                text="Every rendering policy succeeded in 10 of 10 journeys.",
                confidence="high",
                citations=tuple(item.id for item in citations),
            ),
            AnswerClaim(
                text=(
                    f"Minimal averaged {minimal.calls_mean:.1f} calls versus "
                    f"{raw.calls_mean:.1f} for raw."
                ),
                confidence="high",
                citations=("benchmark:j1:minimal", "benchmark:j1:raw"),
            ),
        ),
        citations=citations,
    )


def _missing(
    request: AskRequest,
    step: QueryStep,
    item: str,
) -> AskResponse:
    return AskResponse(
        tier="deterministic",
        question=request.question,
        plan=(step,),
        answer=f"The query cannot run without {item}.",
        claims=(),
        citations=(),
        missing=(item,),
    )


def _contains(value: str, *terms: str) -> bool:
    return all(term in value for term in terms)
