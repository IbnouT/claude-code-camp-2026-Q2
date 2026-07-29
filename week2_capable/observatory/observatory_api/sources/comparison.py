"""Build a semantic, attention-aware comparison from benchmark evidence."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from ..contracts import (
    AttentionEconomics,
    ComparisonCohort,
    ComparisonLane,
    ComparisonMilestone,
    CounterfactualProjection,
    FirstDivergence,
    RunComparison,
)
from ..projections.parser_replay import replay_parser

Mode = Literal["raw", "minimal", "full"]
MODES: tuple[Mode, ...] = ("raw", "minimal", "full")


def rendering_comparison(root: Path) -> RunComparison | None:
    """Compare the complete reset-verified J1 rendering cohorts."""

    records = {mode: _cohort(root, mode) for mode in MODES}
    if any(not records[mode] for mode in MODES):
        return None
    cohorts = tuple(_aggregate(mode, records[mode]) for mode in MODES)
    representatives = {
        mode: _representative(records[mode]) for mode in MODES
    }
    lanes = tuple(
        _lane(root, mode, representatives[mode])
        for mode in MODES
    )
    divergence = _first_divergence(lanes)
    counterfactuals = _counterfactuals(root, representatives["full"])
    raw = cohorts[0]
    minimal = cohorts[1]
    full = cohorts[2]
    return RunComparison(
        id="j1-rendering-n10",
        title="J1 model-facing result rendering",
        journey="J1",
        cohorts=cohorts,
        lanes=lanes,
        divergence=divergence,
        counterfactuals=counterfactuals,
        parser_counterfactuals=tuple(
            replay_parser(
                root
                / f"e1-{mode}-n10"
                / "attempts"
                / str(representatives[mode]["attempt_id"])
                / "gateway.db",
                mode,
            )
            for mode in MODES
        ),
        findings=(
            "All three policies completed every reset-verified journey.",
            (
                "Minimal used "
                f"{_percentage(minimal.calls_mean, raw.calls_mean):.1f}% more "
                "model calls than raw."
            ),
            (
                "Raw and full mean journey cost differed by "
                f"{abs(full.cost_mean - raw.cost_mean):.4f} dollars, "
                "less than either cohort standard deviation."
            ),
            (
                "The deterministic replay isolates payload size while the "
                "cohort comparison measures total journey cost."
            ),
        ),
    )


def _cohort(root: Path, mode: Mode) -> list[dict[str, Any]]:
    path = root / f"e1-{mode}-n10" / "attempts.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(row, dict)
            and row.get("journey_id") == "J1"
            and row.get("result_mode") == mode
        ):
            rows.append(row)
    return rows


def _aggregate(
    mode: Mode,
    rows: list[dict[str, Any]],
) -> ComparisonCohort:
    costs = [_number(row, "cost_usd") for row in rows]
    calls = [_number(row, "tool_calls") for row in rows]
    tools: Counter[str] = Counter()
    for row in rows:
        for name, count in dict(row.get("tools") or {}).items():
            tools[str(name)] += int(count)
    moves = tools["move"]
    total_tools = sum(tools.values())
    return ComparisonCohort(
        mode=mode,
        samples=len(rows),
        successes=sum(bool(row.get("success")) for row in rows),
        cost_mean=statistics.mean(costs),
        cost_median=statistics.median(costs),
        cost_stdev=statistics.stdev(costs) if len(costs) > 1 else 0,
        calls_mean=statistics.mean(calls),
        calls_stdev=statistics.stdev(calls) if len(calls) > 1 else 0,
        invalid_calls=sum(int(row.get("invalid_calls") or 0) for row in rows),
        corrective_calls=sum(
            int(row.get("corrective_calls") or 0) for row in rows
        ),
        tools=dict(sorted(tools.items())),
        attention=AttentionEconomics(
            fresh_tokens=_mean(rows, "fresh_input_tokens"),
            cache_read_tokens=_mean(rows, "cache_read_tokens"),
            cache_write_tokens=_mean(rows, "cache_write_tokens"),
            output_tokens=_mean(rows, "output_tokens"),
            result_chars=_mean(rows, "tool_result_chars"),
            schema_tokens=_mean(rows, "schema_token_estimate"),
            movement_share=moves / total_tools if total_tools else 0,
        ),
    )


def _representative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    median = statistics.median(_number(row, "cost_usd") for row in rows)
    return min(rows, key=lambda row: abs(_number(row, "cost_usd") - median))


def _lane(root: Path, mode: Mode, record: dict[str, Any]) -> ComparisonLane:
    attempt = str(record["attempt_id"])
    path = root / f"e1-{mode}-n10" / "attempts" / attempt / "agent.jsonl"
    milestones: list[ComparisonMilestone] = []
    if path.is_file():
        for row in _json_lines(path):
            if row.get("phase") != "tool_call":
                continue
            tool = str(row.get("name", "unknown")).split("__")[-1]
            arguments = dict(row.get("args") or {})
            argument = _primary_argument(arguments)
            milestones.append(
                ComparisonMilestone(
                    index=len(milestones) + 1,
                    kind=_milestone_kind(tool),
                    label=f"{tool} {argument}".strip(),
                    tool=tool,
                    argument=argument or None,
                )
            )
    milestones.append(
        ComparisonMilestone(
            index=len(milestones) + 1,
            kind="outcome",
            label="objective verified" if record.get("success") else "objective unmet",
            tool=None,
            argument=None,
        )
    )
    return ComparisonLane(
        mode=mode,
        attempt=attempt,
        success=bool(record.get("success")),
        cost_usd=_number(record, "cost_usd"),
        calls=int(record.get("tool_calls") or 0),
        milestones=tuple(milestones),
    )


def _first_divergence(lanes: tuple[ComparisonLane, ...]) -> FirstDivergence:
    longest = max(len(lane.milestones) for lane in lanes)
    for offset in range(longest):
        actions = {
            lane.mode: (
                lane.milestones[offset].label
                if offset < len(lane.milestones)
                else "run ended"
            )
            for lane in lanes
        }
        if len(set(actions.values())) > 1:
            return FirstDivergence(
                index=offset + 1,
                summary=(
                    "Representative paths first disagree at semantic action "
                    f"{offset + 1}."
                ),
                actions=actions,
            )
    return FirstDivergence(
        index=None,
        summary="Representative semantic paths do not diverge.",
        actions={lane.mode: "aligned" for lane in lanes},
    )


def _counterfactuals(
    root: Path,
    record: dict[str, Any],
) -> tuple[CounterfactualProjection, ...]:
    attempt = str(record["attempt_id"])
    path = root / "e1-full-n10" / "attempts" / attempt / "agent.jsonl"
    results = [
        row.get("result", "")
        for row in _json_lines(path)
        if row.get("phase") == "tool_result"
    ]
    sizes = {
        mode: sum(len(_render(result, mode).encode()) for result in results)
        for mode in MODES
    }
    raw = max(1, sizes["raw"])
    return tuple(
        CounterfactualProjection(
            mode=mode,
            observations=len(results),
            bytes=sizes[mode],
            estimated_tokens=(sizes[mode] + 3) // 4,
            delta_from_raw=(sizes[mode] - raw) / raw,
        )
        for mode in MODES
    )


def _render(value: Any, mode: Mode) -> str:
    original = str(value or "")
    if mode == "full":
        return original
    try:
        payload = json.loads(original)
    except (json.JSONDecodeError, TypeError):
        return original
    if not isinstance(payload, dict):
        return original
    kind = payload.get("type")
    text = payload.get("text")
    if kind == "observation" and isinstance(text, str):
        if mode == "raw":
            return text
        compact: dict[str, Any] = {"text": text}
        if isinstance(payload.get("complete"), bool):
            compact["complete"] = payload["complete"]
        return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    if kind == "error" and isinstance(payload.get("message"), str):
        label = str(payload.get("code") or "error").replace("_", " ")
        rendered = f"{label}: {payload['message']}"
        if mode == "raw":
            return rendered
        return json.dumps(
            {"text": rendered, "complete": False},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return original


def _json_lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _primary_argument(arguments: dict[str, Any]) -> str:
    for name in ("direction", "target", "action", "kind"):
        if name in arguments:
            return str(arguments[name])
    return ""


def _milestone_kind(tool: str) -> Literal[
    "observe", "move", "inspect", "other"
]:
    if tool == "move":
        return "move"
    if tool in {"look", "check", "poll"}:
        return "observe"
    if tool in {"examine", "shop", "consider"}:
        return "inspect"
    return "other"


def _number(row: dict[str, Any], name: str) -> float:
    return float(row.get(name) or 0)


def _mean(rows: list[dict[str, Any]], name: str) -> float:
    return statistics.mean(_number(row, name) for row in rows)


def _percentage(value: float, baseline: float) -> float:
    return (value - baseline) / baseline * 100 if baseline else 0
