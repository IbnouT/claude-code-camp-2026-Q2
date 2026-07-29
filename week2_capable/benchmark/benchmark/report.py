"""Append machine rows and render an escaped human report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .metrics import (
    LEGACY_WEEK1_MOVES,
    LEGACY_WEEK1_TOTAL,
    AttemptMetrics,
    CorpusMetrics,
    aggregate,
)


def append_jsonl(path: Path, row: AttemptMetrics) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row.as_dict(), sort_keys=True) + "\n")


def read_rows(path: Path) -> list[AttemptMetrics]:
    if not path.is_file():
        return []
    rows: list[AttemptMetrics] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        value["evidence"] = tuple(value.get("evidence") or ())
        value["wire_sequences"] = tuple(value.get("wire_sequences") or ())
        value["tool_arguments"] = tuple(tuple(item) for item in value.get("tool_arguments") or ())
        value.setdefault("result_mode", "full")
        value.setdefault("tool_result_chars", 0)
        rows.append(AttemptMetrics(**value))
    return rows


def write_markdown(
    path: Path,
    rows: Iterable[AttemptMetrics],
    *,
    corpus: CorpusMetrics | None = None,
) -> None:
    material = list(rows)
    totals = aggregate(material)
    lines = [
        "# E1 benchmark report",
        "",
        "Only complete, priced attempts enter the aggregate.",
        "",
        "| Attempt | Journey | Result | Cost | Model calls | Tool calls | Reset | Sources |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in material:
        result = "PASS" if row.success else _escape(row.stop_reason)
        cost = "unpriced" if row.cost_usd is None else f"${row.cost_usd:.6f}"
        sources = f"`{_escape(row.agent_log)}`<br>`{_escape(row.gateway_journal)}`"
        lines.append(
            f"| {_escape(row.attempt_id)} | {_escape(row.journey_id)} | {result} | "
            f"{cost} | {row.model_calls} | {row.tool_calls} | "
            f"{_escape(row.reset_id or 'none')} | {sources} |"
        )
    if corpus is not None:
        terminal = corpus.executed_total - corpus.confirmed_total
        lines.extend(
            [
                "",
                "## Week 1 reference audit",
                "",
                f"- Executed calls: {corpus.executed_total}, including "
                f"{corpus.executed_by_tool.get('move', 0)} moves.",
                f"- Context-confirmed calls: {corpus.confirmed_total}, including "
                f"{corpus.confirmed_by_tool.get('move', 0)} moves.",
                f"- Terminal calls absent from a later prompt: {terminal}.",
                f"- Legacy working figure: {LEGACY_WEEK1_TOTAL} calls and "
                f"{LEGACY_WEEK1_MOVES} moves. The corpus has no twentieth look, "
                "so this figure is comparison-only.",
            ]
        )
    if material:
        baseline_moves = 316 / 451
        lines.extend(
            [
                "",
                "## Attempt measurements",
                "",
                "| Attempt | Stop | Iterations | Mode | Profile | Schema bytes | "
                "Schema token estimate | Fresh | Cache read | Cache write | Output | "
                "Result chars | Invalid | Corrective | Parse misses |",
                "|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in material:
            profile = _escape(
                f"{row.profile_id or 'unknown'} / {row.capability_digest or 'unknown'}"
            )
            lines.append(
                f"| {_escape(row.attempt_id)} | {_escape(row.stop_reason)} | "
                f"{row.iterations} | {_escape(row.result_mode)} | {profile} | "
                f"{row.schema_bytes} | "
                f"{row.schema_token_estimate} | {row.fresh_input_tokens} | "
                f"{row.cache_read_tokens} | {row.cache_write_tokens} | "
                f"{row.output_tokens} | {row.tool_result_chars} | "
                f"{row.invalid_calls} | "
                f"{row.corrective_calls} | {row.parse_misses} |"
            )
        lines.extend(
            [
                "",
                "## Tool distribution",
                "",
                "| Attempt | Moves | Move share | Difference from Week 1 | All tools |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for row in material:
            moves = row.tools.get("move", 0)
            share = moves / row.tool_calls if row.tool_calls else 0.0
            tools = _escape(json.dumps(row.tools, sort_keys=True))
            lines.append(
                f"| {_escape(row.attempt_id)} | {moves} | {share:.1%} | "
                f"{share - baseline_moves:+.1%} | `{tools}` |"
            )
    lines.extend(
        [
            "",
            "## Aggregate",
            "",
            f"- Eligible attempts: {totals['attempts']}",
            f"- Setup failures excluded: {totals['setup_failures']}",
            f"- Successful journeys: {totals['successes']} / {totals['attempts']}",
            f"- Success rate: {totals['success_rate']:.1%}",
            f"- Model calls: {totals['model_calls']}",
            f"- Tool calls: {totals['tool_calls']}",
            f"- Cost: ${totals['cost_usd']:.6f}",
            "",
            "| Metric | Mean | Median | Standard deviation |",
            "|---|---:|---:|---:|",
        ]
    )
    labels = {
        "cost_usd": "Cost, USD",
        "model_calls": "Model calls",
        "tool_calls": "Tool calls",
        "invalid_calls": "Invalid calls",
        "corrective_calls": "Corrective calls",
        "fresh_input_tokens": "Fresh input tokens",
        "cache_read_tokens": "Cache read tokens",
        "cache_write_tokens": "Cache write tokens",
        "output_tokens": "Output tokens",
    }
    for name, label in labels.items():
        distribution = totals["distributions"][name]
        precision = 6 if name == "cost_usd" else 1
        lines.append(
            f"| {label} | {distribution['mean']:.{precision}f} | "
            f"{distribution['median']:.{precision}f} | "
            f"{distribution['stdev']:.{precision}f} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _escape(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("`", "\\`")
    )
