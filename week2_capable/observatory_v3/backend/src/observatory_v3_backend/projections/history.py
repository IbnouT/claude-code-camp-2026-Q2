"""Cross-session diagnostic history derived from benchmark evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict

from ..contracts import DiagnosticHistory, DiagnosticHistoryItem
from ..sources.benchmark import BenchmarkSource
from ..sources.recorded_session import RecordedSessionSource


class _DiagnosticCounts(TypedDict):
    runs: int
    critical: int
    warning: int
    notice: int
    latest_run: str
    run_ids: list[str]


def diagnostic_history(
    source: BenchmarkSource,
    *,
    recorded: RecordedSessionSource | None = None,
    player_id: str | None = None,
) -> DiagnosticHistory:
    """Aggregate deterministic findings without treating absence as success."""

    runs = source.runs()
    if player_id is not None:
        owned = (
            {item.id for item in recorded.catalog() if item.player_id == player_id}
            if recorded is not None
            else set()
        )
        runs = tuple(run for run in runs if run.id in owned)
    counts: dict[str, _DiagnosticCounts] = defaultdict(
        lambda: {
            "runs": 0,
            "critical": 0,
            "warning": 0,
            "notice": 0,
            "latest_run": "",
            "run_ids": [],
        }
    )
    for run in runs:
        investigation = source.investigation(run.id)
        if investigation is None:
            continue
        seen: set[str] = set()
        for diagnostic in investigation.diagnostics:
            row = counts[diagnostic.kind]
            if diagnostic.kind not in seen:
                row["runs"] += 1
                row["run_ids"].append(run.id)
                seen.add(diagnostic.kind)
            if diagnostic.severity == "critical":
                row["critical"] += 1
            elif diagnostic.severity == "warning":
                row["warning"] += 1
            else:
                row["notice"] += 1
            if not row["latest_run"]:
                row["latest_run"] = run.label

    items = tuple(
        DiagnosticHistoryItem(
            kind=kind,
            runs=values["runs"],
            critical=values["critical"],
            warning=values["warning"],
            notice=values["notice"],
            latest_run=values["latest_run"],
            run_ids=tuple(values["run_ids"]),
        )
        for kind, values in sorted(
            counts.items(),
            key=lambda item: (-item[1]["runs"], item[0]),
        )
    )
    return DiagnosticHistory(
        player_id=player_id,
        total_runs=len(runs),
        successful_runs=sum(run.success for run in runs),
        failed_runs=sum(not run.success for run in runs),
        items=items,
    )
