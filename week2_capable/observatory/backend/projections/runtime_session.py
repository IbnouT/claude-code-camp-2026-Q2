"""Universal recorded-session projection over launcher-owned evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mud_gateway.journal import Event

from ..contracts import (
    EvidenceForm,
    EvidenceLens,
    RuntimeSessionInvestigation,
    RuntimeSessionSummary,
    SessionCostLedger,
    SessionCostPoint,
    SessionDiagnostic,
    SessionEvidenceRecord,
)
from ..redaction import sanitize_evidence
from ..sources.runtime import RuntimeSession
from .live import project_live

#: Agent-log members that carry the conversation and grow with the run.
#: The story withholds them and one endpoint serves them per record.
WITHHELD_FIELDS = ("messages", "request", "response", "tools", "system")


def withheld_agent_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Sanitize the members one record withholds from the session story."""
    return sanitize_evidence(
        {
            key: value
            for key, value in event.items()
            if key in WITHHELD_FIELDS
        }
    )


def project_runtime_session(
    session: RuntimeSession,
    gateway_events: list[Event],
    agent_events: list[dict[str, Any]],
    *,
    atlas: Any = None,
    operator_messages: list[dict[str, Any]] | None = None,
) -> RuntimeSessionInvestigation:
    """Project any launcher run, including empty and interrupted captures."""
    messages = operator_messages or []
    snapshot = project_live(
        session,
        gateway_events,
        agent_events,
        atlas=atlas,
        operator_messages=messages,
    )
    agent_records, trace_parents = _agent_records(agent_events)
    operator_records = _operator_records(messages, agent_records)
    gateway_records = _gateway_records(
        gateway_events,
        trace_parents,
        {
            record.id: (record.iteration, record.turn)
            for record in agent_records
        },
    )
    records = tuple(
        sorted(
            (*agent_records, *operator_records, *gateway_records),
            key=lambda record: (
                _record_epoch(record),
                0 if record.source == "agent" else 1,
                record.sequence,
            ),
        )
    )
    cost_points = _cost_points(agent_events)
    total_cost = round(sum(point.cost_usd for point in cost_points), 8)
    usage = _usage(agent_events)
    capture_gaps = tuple(dict.fromkeys(
        (*snapshot.capture_gaps, *_evidence_capture_gaps(agent_events, gateway_events))
    ))
    diagnostics = _instrumentation_diagnostics(capture_gaps, records)
    iterations = sum(
        event.get("phase") == "iteration" for event in agent_events
    )
    turns = sum(event.get("phase") == "turn" for event in agent_events)
    responses = sum(event.get("phase") == "response" for event in agent_events)
    goal_epochs = session.goal_count
    duration_ms = _duration_ms(session.created_at, session.ended_at)
    objective = session.objective or (
        snapshot.objective_context.title
        if snapshot.objective_context is not None
        else snapshot.objective
    )
    label = objective or f"{session.character} session"
    summary = RuntimeSessionSummary(
        id=session.id,
        label=label,
        attempt=session.id[:8],
        success=session.state == "completed",
        stop_reason=session.stop_mode or session.state,
        iterations=iterations,
        cost_usd=total_cost,
        lifecycle=session.state,
        capture_status=session.capture_status,
        created_at=session.created_at,
        ended_at=session.ended_at,
        duration_ms=duration_ms,
        turns=turns,
        responses=responses,
        goal_epochs=goal_epochs,
    )
    return RuntimeSessionInvestigation(
        correlation=f"runtime:{session.id}",
        run=summary,
        player_id=session.player_id,
        agent_session_id=session.id,
        gateway_session_id=session.gateway_session_id,
        objective=objective,
        model=snapshot.model,
        records=records,
        diagnostics=diagnostics,
        diagnostic_coverage=("instrumentation_gap",),
        lens=_evidence_lens(agent_events, gateway_events),
        world=snapshot.world,
        cost=SessionCostLedger(
            total_usd=total_cost,
            response_total_usd=total_cost,
            raw_response_total_usd=total_cost,
            reconciliation_delta_usd=0,
            complete=bool(agent_events) and "agent_events_missing" not in capture_gaps,
            completeness_detail=(
                "Sum of retained agent response costs."
                if agent_events
                else "No agent response ledger was retained."
            ),
            fresh_input_tokens=usage["fresh_input"],
            cache_read_tokens=usage["cache_read"],
            cache_write_tokens=usage["cache_write"],
            output_tokens=usage["output"],
            points=cost_points,
        ),
        capture_gaps=capture_gaps,
    )


def _agent_records(
    events: list[dict[str, Any]],
) -> tuple[list[SessionEvidenceRecord], dict[str, str]]:
    records: list[SessionEvidenceRecord] = []
    trace_parents: dict[str, str] = {}
    root: str | None = None
    turn: str | None = None
    iteration: str | None = None
    prompt: str | None = None
    response: str | None = None
    model_request: str | None = None
    provider_response: str | None = None
    tool_calls: dict[str, str] = {}
    turn_number = 0
    iteration_number = 0
    legacy_turn_instructions = _legacy_turn_instructions(events)
    for event in events:
        line = _integer(event.get("line"))
        phase = str(event.get("phase") or "event")
        if phase == "turn" and not event.get("instruction"):
            event = {
                **event,
                "instruction": legacy_turn_instructions.get(line),
            }
        record_id = f"agent:{line}"
        parent = root
        if phase == "session_start":
            root = record_id
            parent = None
        elif phase == "turn":
            turn_number = _integer(event.get("n")) or turn_number + 1
            turn = record_id
            iteration = None
            iteration_number = 0
            prompt = None
            response = None
            model_request = None
            provider_response = None
            parent = root
        elif phase == "iteration":
            iteration_number = _integer(event.get("n")) or iteration_number + 1
            iteration = record_id
            prompt = None
            response = None
            model_request = None
            provider_response = None
            parent = turn or root
        elif phase == "prompt":
            prompt = record_id
            parent = iteration or turn or root
        elif phase == "model_request":
            model_request = record_id
            parent = prompt or iteration or turn or root
        elif phase == "provider_response":
            provider_response = record_id
            parent = model_request or prompt or iteration or turn or root
        elif phase in {"plan", "belief", "reasoning"}:
            parent = provider_response or model_request or prompt or iteration or turn or root
        elif phase == "response":
            response = record_id
            parent = provider_response or model_request or prompt or iteration or turn or root
        elif phase == "raw":
            parent = provider_response or model_request or prompt or iteration or turn or root
        elif phase == "tool_call":
            parent = response or iteration or turn or root
            tool_id = event.get("id")
            if isinstance(tool_id, str):
                tool_calls[tool_id] = record_id
        elif phase == "tool_result":
            tool_id = event.get("tool_use_id")
            parent = (
                tool_calls.get(tool_id)
                if isinstance(tool_id, str)
                else None
            ) or response or iteration or turn or root
            trace = _tool_result_trace(event.get("result"))
            stages = event.get("stages")
            if trace is None and isinstance(stages, dict):
                trace = _tool_result_trace(stages.get("mcp_result"))
            if trace is not None:
                trace_parents[trace] = parent
        cost = (
            _number(event.get("cost_usd"))
            if phase == "response"
            else 0
        )
        usage = event.get("usage")
        tokens = _usage_total(usage) if isinstance(usage, dict) else 0
        records.append(
            SessionEvidenceRecord(
                id=record_id,
                parent_id=parent,
                source="agent",
                form=_agent_form(phase),
                kind=phase,
                label=_agent_label(event, phase),
                sequence=line,
                at=str(event.get("at") or ""),
                trace_id=None,
                iteration=iteration_number or None,
                turn=turn_number or None,
                duration_ms=_number(event.get("duration_ms")),
                cost_usd=cost,
                tokens=tokens,
                status=_agent_status(event, phase),
                preview=_agent_preview(event, phase),
                fields=_agent_fields(event),
                source_ref=f"agent.jsonl line {line}",
            )
        )
    return records, trace_parents


def _operator_records(
    messages: list[dict[str, Any]],
    agent_records: list[SessionEvidenceRecord],
) -> list[SessionEvidenceRecord]:
    """Project accepted guidance into its actual model-visible boundary."""
    boundaries = [
        record for record in agent_records if record.kind == "iteration"
    ]
    sequence = max((record.sequence for record in agent_records), default=0)
    records: list[SessionEvidenceRecord] = []
    for index, message in enumerate(messages, start=1):
        action = message.get("action")
        instruction = message.get("instruction")
        sent_at = message.get("sent_at")
        applied_at = message.get("applied_at")
        if (
            action not in {"guide", "revise"}
            or not isinstance(instruction, str)
            or not isinstance(sent_at, str)
        ):
            continue
        effective_at = applied_at if isinstance(applied_at, str) else sent_at
        boundary = next(
            (
                record
                for record in boundaries
                if _timestamp(record.at) >= _timestamp(effective_at)
            ),
            None,
        )
        request_id = str(message.get("request_id") or index)
        kind = "goal_revision" if action == "revise" else "guidance"
        records.append(
            SessionEvidenceRecord(
                id=f"operator:{request_id}",
                parent_id=boundary.id if boundary is not None else None,
                source="agent",
                form="rendered",
                kind=kind,
                label="Goal" if action == "revise" else "Nudge",
                sequence=sequence + index,
                at=effective_at,
                trace_id=None,
                iteration=boundary.iteration if boundary is not None else None,
                turn=boundary.turn if boundary is not None else None,
                duration_ms=0,
                cost_usd=0,
                tokens=0,
                status="complete" if isinstance(applied_at, str) else "partial",
                preview=instruction.strip(),
                fields=sanitize_evidence(
                    {
                        "request_id": request_id,
                        "action": action,
                        "instruction": instruction.strip(),
                        "sent_at": sent_at,
                        "applied_at": applied_at,
                        "applied_iteration": message.get("applied_iteration"),
                        "insertion": "next_iteration_boundary",
                    }
                ),
                source_ref="operator-messages.json",
            )
        )
    return records


def _gateway_records(
    events: list[Event],
    trace_parents: dict[str, str],
    agent_scopes: dict[str, tuple[int | None, int | None]],
) -> list[SessionEvidenceRecord]:
    records: list[SessionEvidenceRecord] = []
    last_by_trace: dict[str, str] = {}
    scopes = dict(agent_scopes)
    for event in events:
        record_id = f"gateway:{event.seq}"
        parent = None
        if event.trace_id:
            parent = last_by_trace.get(event.trace_id) or trace_parents.get(
                event.trace_id
            )
            last_by_trace[event.trace_id] = record_id
        iteration, turn = scopes.get(parent or "", (None, None))
        scopes[record_id] = (iteration, turn)
        records.append(
            SessionEvidenceRecord(
                id=record_id,
                parent_id=parent,
                source="gateway",
                form=_gateway_form(event.kind),
                kind=event.kind,
                label=_gateway_label(event),
                sequence=event.seq,
                at=_iso(event.at),
                trace_id=event.trace_id,
                iteration=iteration,
                turn=turn,
                room_id=_room_id(event.payload),
                status=_gateway_status(event),
                preview=_gateway_preview(event),
                fields=dict(event.payload),
                source_ref=f"gateway.db event {event.seq}",
            )
        )
    return records


def _cost_points(
    events: list[dict[str, Any]],
) -> tuple[SessionCostPoint, ...]:
    points: list[SessionCostPoint] = []
    iteration = 0
    response_number = 0
    for event in events:
        if event.get("phase") == "iteration":
            iteration = _integer(event.get("n")) or iteration
        if event.get("phase") != "response":
            continue
        response_number += 1
        usage = event.get("usage")
        normalized = usage if isinstance(usage, dict) else {}
        fresh = _integer(
            normalized.get("input_tokens")
            or normalized.get("prompt_tokens")
        )
        cache_read = _integer(
            normalized.get("cache_read_input_tokens")
            or normalized.get("cached_tokens")
        )
        cache_write = _integer(
            normalized.get("cache_creation_input_tokens")
            or normalized.get("cache_write_tokens")
        )
        output = _integer(
            normalized.get("output_tokens")
            or normalized.get("completion_tokens")
        )
        cost = _number(event.get("cost_usd"))
        points.append(
            SessionCostPoint(
                record_id=f"agent:{_integer(event.get('line'))}",
                iteration=iteration or None,
                cost_usd=cost,
                raw_response_cost_usd=cost,
                pricing_source="agent_response",
                fresh_input_tokens=fresh,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                output_tokens=output,
                context_tokens=fresh + cache_read + cache_write,
                progress=f"response {response_number}",
            )
        )
    return tuple(points)


def _usage(events: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "fresh_input": 0,
        "cache_read": 0,
        "cache_write": 0,
        "output": 0,
    }
    for event in events:
        if event.get("phase") != "response":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        totals["fresh_input"] += _integer(
            usage.get("input_tokens") or usage.get("prompt_tokens")
        )
        totals["cache_read"] += _integer(
            usage.get("cache_read_input_tokens") or usage.get("cached_tokens")
        )
        totals["cache_write"] += _integer(
            usage.get("cache_creation_input_tokens")
            or usage.get("cache_write_tokens")
        )
        totals["output"] += _integer(
            usage.get("output_tokens") or usage.get("completion_tokens")
        )
    return totals


def _instrumentation_diagnostics(
    capture_gaps: tuple[str, ...],
    records: tuple[SessionEvidenceRecord, ...],
) -> tuple[SessionDiagnostic, ...]:
    if not capture_gaps:
        return ()
    first = records[0].id if records else "session"
    return (
        SessionDiagnostic(
            id="diagnostic:capture",
            kind="instrumentation_gap",
            severity="warning",
            state="open",
            title="Some evidence dimensions were not observed",
            consequence="The available run can be followed, but some conclusions remain bounded.",
            rule_version="runtime-capture-v1",
            threshold="one or more required evidence dimensions missing",
            at_record=first,
            evidence=tuple(capture_gaps),
            alternatives=("The source may not emit this dimension.",),
            affected_conclusions=("Claims that depend on missing evidence",),
        ),
    )


def _evidence_capture_gaps(
    agent_events: list[dict[str, Any]],
    gateway_events: list[Event],
) -> tuple[str, ...]:
    """Name missing transformation stages without guessing their content."""
    phases = {str(event.get("phase") or "") for event in agent_events}
    gaps: list[str] = []
    if "response" in phases and "model_request" not in phases:
        gaps.append("model_request_body_not_retained")
    if "response" in phases and "provider_response" not in phases:
        gaps.append("provider_response_body_not_retained")
    transformed_results = [
        event
        for event in agent_events
        if event.get("phase") == "tool_result"
        and isinstance(event.get("name"), str)
        and "__" in str(event.get("name"))
    ]
    if transformed_results and any(
        not isinstance(event.get("stages"), dict)
        for event in transformed_results
    ):
        gaps.append("tool_result_transform_stages_not_retained")
    gateway_kinds = {event.kind for event in gateway_events}
    if (
        gateway_kinds & {"command", "observation", "tool_result"}
        and "wire" not in gateway_kinds
    ):
        gaps.append("original_mud_wire_not_retained")
    if (
        gateway_kinds & {"wire", "observation", "unparsed"}
        and not {"wire_text", "parser_input"}.issubset(gateway_kinds)
    ):
        gaps.append("mud_text_transform_stages_not_retained")
    return tuple(gaps)


def _evidence_lens(
    agent_events: list[dict[str, Any]],
    gateway_events: list[Event],
) -> EvidenceLens:
    kinds = {event.kind for event in gateway_events}
    model_wire = any(
        event.get("phase") in {"model_request", "provider_response"}
        for event in agent_events
    )
    return EvidenceLens(
        wire=_form(
            "Wire",
            "Original model and MUD transport evidence.",
            "wire" in kinds or model_wire,
        ),
        parsed=_form(
            "Parsed",
            "Gateway parser observations and unmatched lines.",
            bool(kinds & {"observation", "unparsed", "position"}),
        ),
        rendered=_form(
            "Rendered",
            "Model responses, tools, and gateway commands.",
            bool(agent_events) or bool(kinds & {"command", "tool_result"}),
        ),
        believed=_form(
            "Believed",
            "Retained agent plans and reasoning.",
            any(
                event.get("phase") in {"plan", "belief", "reasoning"}
                for event in agent_events
            ),
        ),
        truth=_form(
            "Truth",
            "Direct runtime lifecycle and observed world state.",
            bool(agent_events) or bool(gateway_events),
        ),
    )


def _form(title: str, text: str, available: bool) -> EvidenceForm:
    return EvidenceForm(
        state="available" if available else "missing",
        title=title,
        text=text if available else f"{title} evidence was not retained.",
    )


def _agent_form(phase: str) -> str:
    if phase in {"model_request", "provider_response", "raw"}:
        return "wire"
    if phase in {"plan", "belief", "reasoning"}:
        return "believed"
    if phase in {"session_start", "turn", "iteration", "turn_end"}:
        return "truth"
    return "rendered"


def _gateway_form(kind: str) -> str:
    if kind in {"wire", "wire_text"}:
        return "wire"
    if kind in {
        "parser_input",
        "observation",
        "unparsed",
        "position",
        "parse_metric",
    }:
        return "parsed"
    if kind in {"command", "tool_result"}:
        return "rendered"
    return "truth"


def _agent_label(event: dict[str, Any], phase: str) -> str:
    if phase == "turn":
        return f"Turn {_integer(event.get('n'))}"
    if phase == "iteration":
        return f"Iteration {_integer(event.get('n'))}"
    if phase == "tool_call":
        return f"Tool call · {event.get('name') or 'unknown'}"
    if phase == "tool_result":
        return f"Tool result · {event.get('name') or 'unknown'}"
    if phase == "response":
        return f"Model response · {event.get('model') or 'unknown model'}"
    if phase == "model_request":
        return f"Model request · {event.get('model') or 'unknown model'}"
    if phase == "provider_response":
        return f"Provider response · {event.get('model') or 'unknown model'}"
    if phase == "session_start":
        return "Session started"
    return phase.replace("_", " ").title()


def _gateway_label(event: Event) -> str:
    if event.kind == "command":
        return f"Gateway command · {event.payload.get('line') or 'unknown'}"
    if event.kind == "wire":
        return f"Wire {event.payload.get('direction') or 'event'}"
    if event.kind == "wire_text":
        return f"Decoded wire text · {event.payload.get('direction') or 'event'}"
    if event.kind == "parser_input":
        return "Normalized parser input"
    detail = (
        event.payload.get("kind")
        or event.payload.get("tool")
        or event.kind
    )
    return f"{event.kind.replace('_', ' ').title()} · {detail}"


def _agent_preview(event: dict[str, Any], phase: str) -> str:
    if phase == "turn":
        return _preview(sanitize_evidence(event.get("instruction")))
    if phase == "prompt":
        messages = event.get("messages")
        if isinstance(messages, list) and messages:
            return _preview(sanitize_evidence(messages[-1]))
    if phase == "model_request":
        return _preview(sanitize_evidence(event.get("request")))
    if phase == "provider_response":
        return _preview(sanitize_evidence(event.get("response")))
    if phase in {"plan", "belief", "reasoning", "response"}:
        return _preview(sanitize_evidence(event.get("text")))
    if phase == "tool_call":
        return _preview(sanitize_evidence(event.get("args")))
    if phase == "tool_result":
        return _preview(sanitize_evidence(event.get("result")))
    if phase == "session_start":
        objective = event.get("objective")
        if isinstance(objective, dict):
            return _preview(objective.get("title"))
    return _preview(event.get("task") or event.get("stop_reason") or phase)


def _gateway_preview(event: Event) -> str:
    return _preview(
        event.payload.get("text")
        or event.payload.get("line")
        or event.payload
    )


def _agent_fields(event: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "phase",
        "at",
        "n",
        "model",
        "provider",
        "duration_ms",
        "cost_usd",
        "usage",
        "stop_reason",
        "name",
        "id",
        "tool_use_id",
        "args",
        "ok",
        "error",
        "context_window",
        "message_count",
        "content",
        "data",
        "tool_count",
        "text",
        "result",
        "stages",
        "task",
        "instruction",
        "objective",
        "schema",
        "max_iterations",
        "max_turn_tokens",
        "max_turn_cost",
        "max_output_tokens",
        "rates",
        "cache_min_tokens",
        "caches",
        "request_id",
        "action",
        "state",
        "iteration",
    }
    carried = {key: value for key, value in event.items() if key in allowed}
    # The system prompt is withheld everywhere it repeats, and carried here
    # because it appears once for the whole session and is what the model was
    # told to be.
    if event.get("phase") == "session_start":
        system = event.get("system")
        if isinstance(system, str):
            carried["system"] = system
    last_message = _last_message(event)
    if last_message is not None:
        carried["last_message"] = last_message
    return sanitize_evidence(carried)


def _last_message(event: dict[str, Any]) -> dict[str, Any] | None:
    """Carry the final message so a collapsed prompt still reads.

    It is built into the dictionary that is sanitized rather than beside
    it, so it carries the same redaction as every other member.
    """
    messages = event.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    last = messages[-1]
    if not isinstance(last, dict):
        return {"role": "message", "content": last}
    role = last.get("role")
    return {
        "role": role if isinstance(role, str) else "message",
        "content": last.get("content"),
    }


def _agent_status(event: dict[str, Any], phase: str) -> str:
    if phase == "tool_result":
        if event.get("error") or event.get("ok") is False:
            return "failed"
        return "complete"
    if phase == "response" and event.get("stop_reason") == "error":
        return "failed"
    return "complete"


def _gateway_status(event: Event) -> str:
    if event.payload.get("complete") is False:
        return "partial"
    if event.payload.get("error"):
        return "failed"
    return "complete"


def _room_id(payload: dict[str, Any]) -> str | None:
    place = payload.get("place")
    return f"place:{place}" if isinstance(place, int) else None


def _tool_result_trace(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    trace = payload.get("trace_id") if isinstance(payload, dict) else None
    return trace if isinstance(trace, str) else None


def _legacy_turn_instructions(
    events: list[dict[str, Any]],
) -> dict[int, str]:
    """Recover old turn instructions from their first complete prompt."""
    instructions: dict[int, str] = {}
    turn_line: int | None = None
    for event in events:
        phase = event.get("phase")
        if phase == "turn":
            turn_line = _integer(event.get("line"))
            continue
        if phase != "prompt" or turn_line is None or turn_line in instructions:
            continue
        messages = event.get("messages")
        if not isinstance(messages, list):
            continue
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            text = "\n".join(
                str(block.get("text"))
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ).strip()
            if text:
                instructions[turn_line] = text
            break
    return instructions


def _record_epoch(record: SessionEvidenceRecord) -> float:
    try:
        return datetime.fromisoformat(record.at).timestamp()
    except ValueError:
        return 0


def _timestamp(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0


def _duration_ms(start: str, end: str | None) -> float | None:
    if end is None:
        return None
    try:
        return max(
            0,
            (datetime.fromisoformat(end) - datetime.fromisoformat(start))
            .total_seconds()
            * 1000,
        )
    except ValueError:
        return None


def _iso(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _usage_total(usage: dict[str, Any]) -> int:
    return sum(
        _integer(value)
        for key, value in usage.items()
        if "token" in key and not key.endswith("_tokens_details")
    )


def _preview(value: Any, limit: int = 240) -> str:
    if isinstance(value, str):
        text = " ".join(value.split())
    else:
        text = json.dumps(value, sort_keys=True, default=str)
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0
    return float(value) if isinstance(value, (int, float)) else 0


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return int(value) if isinstance(value, (int, float)) else 0
