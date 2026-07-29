"""Cross-session diagnostic history derived from benchmark evidence."""

from __future__ import annotations

from collections import defaultdict

from ..contracts import DiagnosticHistory, DiagnosticHistoryItem
from ..sources.benchmark import BenchmarkSource


def diagnostic_history(source: BenchmarkSource) -> DiagnosticHistory:
    """Aggregate deterministic findings without treating absence as success."""

    runs = source.runs()
    counts: dict[str, dict[str, int | str]] = defaultdict(
        lambda: {
            "runs": 0,
            "critical": 0,
            "warning": 0,
            "notice": 0,
            "latest_run": "",
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
                row["runs"] = int(row["runs"]) + 1
                seen.add(diagnostic.kind)
            row[diagnostic.severity] = int(row[diagnostic.severity]) + 1
            if not row["latest_run"]:
                row["latest_run"] = run.label

    items = tuple(
        DiagnosticHistoryItem(
            kind=kind,
            runs=int(values["runs"]),
            critical=int(values["critical"]),
            warning=int(values["warning"]),
            notice=int(values["notice"]),
            latest_run=str(values["latest_run"]),
        )
        for kind, values in sorted(
            counts.items(),
            key=lambda item: (-int(item[1]["runs"]), item[0]),
        )
    )
    return DiagnosticHistory(
        total_runs=len(runs),
        successful_runs=sum(run.success for run in runs),
        failed_runs=sum(not run.success for run in runs),
        items=items,
    )
