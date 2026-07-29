"""Read agent JSONL and gateway SQLite into one benchmark row."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .journeys import Journey, judge


LEGACY_WEEK1_TOTAL = 448
LEGACY_WEEK1_MOVES = 314


@dataclass(frozen=True)
class CorpusMetrics:
    """Executed and prompt-confirmed calls in the tracked Week 1 corpus."""

    executed_total: int
    executed_by_tool: dict[str, int]
    confirmed_total: int
    confirmed_by_tool: dict[str, int]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class AttemptMetrics:
    """One traceable benchmark attempt."""

    attempt_id: str
    journey_id: str
    status: str
    stop_reason: str
    iterations: int
    success: bool
    evidence: tuple[str, ...]
    final_state: dict[str, Any]
    wall_ms: int
    model_calls: int
    tool_calls: int
    tools: dict[str, int]
    invalid_calls: int
    corrective_calls: int
    fresh_input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    occupancy_tokens: int
    schema_bytes: int
    schema_token_estimate: int
    cost_usd: float | None
    reset_id: str | None
    profile_id: str | None
    result_mode: str
    capability_digest: str | None
    parse_misses: int
    tool_result_chars: int
    wire_sequences: tuple[int, ...]
    agent_log: str
    gateway_journal: str
    error: str | None = None
    tool_arguments: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def aggregate_eligible(self) -> bool:
        return self.status == "complete" and self.cost_usd is not None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON at {path}:{number}") from error
        if isinstance(value, dict):
            rows.append(value)
    return rows


def read_gateway(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT seq, session, kind, trace_id, payload FROM events ORDER BY seq"
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "seq": int(seq),
            "session": session,
            "kind": kind,
            "trace_id": trace_id,
            "payload": json.loads(payload),
        }
        for seq, session, kind, trace_id, payload in rows
    ]


def measure_attempt(
    *,
    attempt_id: str,
    journey: Journey,
    agent_log: Path,
    gateway_journal: Path,
    wall_ms: int,
    process_ok: bool,
    schema_bytes: int,
    schema_token_estimate: int,
    result_mode: str = "full",
    reset_id: str | None = None,
    error: str | None = None,
) -> AttemptMetrics:
    agent = read_jsonl(agent_log)
    gateway = read_gateway(gateway_journal)
    verdict = judge(journey, gateway)
    calls = [row for row in agent if row.get("phase") == "tool_call"]
    results = [row for row in agent if row.get("phase") == "tool_result"]
    responses = [row for row in agent if row.get("phase") == "response"]
    turn_ends = [row for row in agent if row.get("phase") == "turn_end"]
    usage = _usage(responses)
    cost_values = [row.get("cost_usd") for row in turn_ends]
    priced = bool(cost_values) and all(isinstance(value, (int, float)) for value in cost_values)
    cost = round(sum(float(value) for value in cost_values), 8) if priced else None
    completed = process_ok and bool(turn_ends)
    status = "complete" if completed else "incomplete"
    iterations = max(
        (int(row.get("iterations") or 0) for row in turn_ends), default=0
    )
    stop_reason = _stop_reason(
        process_ok=process_ok,
        turn_ends=turn_ends,
        journey_success=verdict.success,
    )

    invalid_ids = {
        str(row.get("tool_use_id"))
        for row in results
        if row.get("ok") is False or row.get("error")
    }
    rejected = [row for row in gateway if row.get("kind") == "tool_rejected"]
    invalid_count = max(len(invalid_ids), len(rejected))
    corrective = _corrective_calls(calls, invalid_ids, len(rejected))
    profiles = [row for row in gateway if row.get("kind") == "surface_profile"]
    profile = profiles[-1].get("payload", {}) if profiles else {}
    observations = [row for row in gateway if row.get("kind") == "observation"]
    final_state = _final_state(gateway)
    misses = sum(1 for row in gateway if row.get("kind") == "unparsed")
    sequences = tuple(int(row["seq"]) for row in observations if row.get("seq") is not None)
    tools = Counter(_bare(str(row.get("name") or "")) for row in calls)
    arguments = tuple(
        (_bare(str(row.get("name") or "")), json.dumps(row.get("args") or {}, sort_keys=True))
        for row in calls
    )
    result_chars = sum(
        len(str(row.get("result") or ""))
        for row in results
    )

    return AttemptMetrics(
        attempt_id=attempt_id,
        journey_id=journey.id,
        status=status,
        stop_reason=stop_reason,
        iterations=iterations,
        success=bool(completed and verdict.success),
        evidence=verdict.evidence,
        final_state=final_state if isinstance(final_state, dict) else {},
        wall_ms=wall_ms,
        model_calls=len(responses),
        tool_calls=len(calls),
        tools=dict(sorted(tools.items())),
        invalid_calls=invalid_count,
        corrective_calls=corrective,
        fresh_input_tokens=usage["fresh"],
        cache_read_tokens=usage["read"],
        cache_write_tokens=usage["write"],
        output_tokens=usage["output"],
        occupancy_tokens=usage["fresh"] + usage["read"] + usage["write"],
        schema_bytes=schema_bytes,
        schema_token_estimate=schema_token_estimate,
        cost_usd=cost,
        reset_id=reset_id,
        profile_id=str(profile.get("profile_id")) if profile.get("profile_id") else None,
        result_mode=result_mode,
        capability_digest=(
            str(profile.get("capability_digest"))
            if profile.get("capability_digest") else None
        ),
        parse_misses=misses,
        wire_sequences=sequences,
        agent_log=str(agent_log),
        gateway_journal=str(gateway_journal),
        error=error,
        tool_arguments=arguments,
        tool_result_chars=result_chars,
    )


def week1_corpus(directory: Path) -> CorpusMetrics:
    """Measure executed calls and calls confirmed in a later prompt."""
    executed: dict[str, str] = {}
    confirmed: dict[str, str] = {}
    sources = tuple(sorted(directory.glob("20260725*.jsonl")))
    for source in sources:
        for row in read_jsonl(source):
            if row.get("phase") == "tool_call" and row.get("id"):
                executed[str(row["id"])] = _bare(str(row.get("name") or ""))
            if row.get("phase") != "prompt":
                continue
            for message in row.get("messages") or ():
                if not isinstance(message, dict) or not isinstance(message.get("content"), list):
                    continue
                for block in message["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        confirmed[str(block.get("id"))] = _bare(str(block.get("name") or ""))
    return CorpusMetrics(
        executed_total=len(executed),
        executed_by_tool=dict(sorted(Counter(executed.values()).items())),
        confirmed_total=len(confirmed),
        confirmed_by_tool=dict(sorted(Counter(confirmed.values()).items())),
        sources=tuple(str(path) for path in sources),
    )


def aggregate(rows: Iterable[AttemptMetrics]) -> dict[str, Any]:
    eligible = [row for row in rows if row.aggregate_eligible]
    return {
        "attempts": len(eligible),
        "successes": sum(row.success for row in eligible),
        "cost_usd": round(sum(row.cost_usd or 0 for row in eligible), 8),
        "tool_calls": sum(row.tool_calls for row in eligible),
        "model_calls": sum(row.model_calls for row in eligible),
    }


def _usage(responses: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    total = {"fresh": 0, "read": 0, "write": 0, "output": 0}
    for row in responses:
        usage = row.get("usage") or {}
        if not isinstance(usage, dict):
            continue
        fresh = _integer(usage, "input_tokens", "prompt_tokens", "promptTokenCount")
        read = _integer(usage, "cache_read_input_tokens", "cached_tokens", "cachedContentTokenCount")
        write = _integer(usage, "cache_creation_input_tokens", "cache_write_tokens")
        if read and ("prompt_tokens" in usage or "promptTokenCount" in usage):
            fresh = max(0, fresh - read)
        total["fresh"] += fresh
        total["read"] += read
        total["write"] += write
        total["output"] += _integer(
            usage, "output_tokens", "completion_tokens", "candidatesTokenCount"
        )
    return total


def _integer(mapping: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def _corrective_calls(
    calls: list[dict[str, Any]], invalid_ids: set[str], rejected_count: int
) -> int:
    positions = {
        index for index, row in enumerate(calls) if str(row.get("id")) in invalid_ids
    }
    followed = sum(1 for index in positions if index + 1 < len(calls))
    unmatched_rejections = max(0, rejected_count - len(positions))
    return followed + min(unmatched_rejections, max(0, len(calls) - followed))


def _final_state(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for event in events:
        kind = event.get("kind")
        payload = event.get("payload")
        if kind == "position" and isinstance(payload, dict):
            state["position"] = payload
        elif kind == "observation" and isinstance(payload, dict):
            observation_kind = payload.get("kind")
            if observation_kind in {"room", "vitals", "exits"}:
                state[str(observation_kind)] = payload
    return state


def _stop_reason(
    *,
    process_ok: bool,
    turn_ends: list[dict[str, Any]],
    journey_success: bool,
) -> str:
    if not process_ok:
        return "process-error"
    if not turn_ends:
        return "missing-turn-end"
    raw = str(turn_ends[-1].get("reason") or "unknown")
    if raw == "completed" and journey_success:
        return "journey-complete"
    if raw == "max_cost":
        return "max_turn_cost"
    return raw


def _bare(name: str) -> str:
    return name.split("__")[-1]
