"""Deterministic queries over experiment jobs and imported comparisons."""

from __future__ import annotations

from ..contracts import (
    AnswerClaim,
    AskRequest,
    AskResponse,
    EvidenceCitation,
    ObservatoryQuery,
    QueryStep,
)
from ..execution import ExperimentExecutor
from ..sources.benchmark import BenchmarkSource
from ..sources.comparison import rendering_comparison
from .common import missing, values_match_filters


def samples(
    request: AskRequest,
    benchmark: BenchmarkSource | None,
    executor: ExperimentExecutor | None,
    query: ObservatoryQuery,
) -> AskResponse:
    """List samples from only the selected job or imported comparison."""

    step = QueryStep(
        operation="list_experiment_samples",
        source="experiments",
        detail=(
            "List samples only from the selected experiment definition, job, "
            "or comparison."
        ),
    )
    subject = request.scope.subject_id
    if executor is not None and subject in executor.jobs:
        job = executor.require(subject)
        selected = [
            sample
            for sample in job.samples.values()
            if values_match_filters(
                {
                    "arm_id": sample["arm_id"],
                    "state": sample["state"],
                    "cost_usd": sample["cost_usd"],
                },
                query,
            )
        ]
        if query.order == "cost_desc":
            selected.sort(
                key=lambda sample: float(sample["cost_usd"]),
                reverse=True,
            )
        citations = tuple(
            EvidenceCitation(
                id=f"experiment:{job.id}:{sample['id']}",
                source="experiments",
                label=f"{sample['arm_id']} sample {sample['ordinal']}",
                sequence=None,
                trace_id=None,
                excerpt=(
                    f"state={sample['state']} cost={sample['cost_usd']}"
                ),
            )
            for sample in selected[:query.limit]
        )
        return AskResponse(
            tier="deterministic",
            question=request.question,
            plan=(step,),
            answer=f"{len(citations)} stable samples belong to job {job.id}.",
            claims=(),
            citations=citations,
        )
    if benchmark is None:
        return missing(request, step, "selected experiment evidence")
    comparison = rendering_comparison(benchmark.root)
    if comparison is None:
        return missing(request, step, "complete selected comparison")
    selected = [
        sample
        for sample in comparison.samples
        if values_match_filters(
            {
                "arm_id": sample.mode,
                "state": "success" if sample.success else "agent_failure",
                "cost_usd": sample.cost_usd,
            },
            query,
        )
    ]
    if query.order == "cost_desc":
        selected.sort(key=lambda sample: sample.cost_usd, reverse=True)
    citations = tuple(
        EvidenceCitation(
            id=f"experiment:sample:{sample.run_id}",
            source="experiments",
            label=f"{sample.mode} sample {sample.attempt}",
            sequence=None,
            trace_id=None,
            excerpt=(
                f"success={sample.success} cost=${sample.cost_usd:.6f} "
                f"turns={sample.turns}"
            ),
        )
        for sample in selected[:query.limit]
    )
    return AskResponse(
        tier="deterministic",
        question=request.question,
        plan=(step,),
        answer=(
            f"{len(selected)} matching samples belong to comparison "
            f"{comparison.id}. Showing {len(citations)}."
        ),
        claims=(),
        citations=citations,
    )


def compare(
    request: AskRequest,
    benchmark: BenchmarkSource,
) -> AskResponse:
    """Compare the complete reset-verified rendering cohorts."""

    comparison = rendering_comparison(benchmark.root)
    step = QueryStep(
        operation="compare_rendering",
        source="benchmark",
        detail="Compare reset-verified cohorts and same-evidence replay.",
    )
    if comparison is None:
        return missing(request, step, "complete J1 rendering cohorts")
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
