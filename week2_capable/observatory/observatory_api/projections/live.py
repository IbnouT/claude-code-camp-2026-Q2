"""Deterministic Live projection over one runtime session prefix."""

from __future__ import annotations

import bisect
from datetime import datetime
from typing import Any

from mud_gateway.journal import Event

from ..contracts import (
    LiveJourneySnapshot,
    LiveRoom,
    LiveTimelineItem,
)
from ..sources.runtime import RuntimeSession


def project_live(
    session: RuntimeSession,
    gateway_events: list[Event],
    agent_events: list[dict[str, Any]],
    *,
    through: int | None = None,
) -> LiveJourneySnapshot:
    latest = gateway_events[-1].seq if gateway_events else 0
    selected = latest if through is None else max(0, min(through, latest))
    gateway_prefix = [event for event in gateway_events if event.seq <= selected]
    selected_at = gateway_prefix[-1].at if gateway_prefix else None
    agent_prefix = [
        event
        for event in agent_events
        if selected_at is None or _stamp(event.get("at")) <= selected_at
    ]
    objective = _objective(agent_prefix)
    session_start = _latest(agent_prefix, "session_start")
    iteration = _latest(agent_prefix, "iteration")
    prompt = _latest(agent_prefix, "prompt")
    response_events = [
        event for event in agent_prefix if event.get("phase") == "response"
    ]
    usage = {
        "fresh_input": 0,
        "cache_read": 0,
        "cache_write": 0,
        "output": 0,
    }
    cost = 0.0
    for event in response_events:
        cost += _number(event.get("cost_usd"))
        raw_usage = event.get("usage")
        if isinstance(raw_usage, dict):
            usage["fresh_input"] += _integer(
                raw_usage.get("input_tokens")
                or raw_usage.get("prompt_tokens")
            )
            usage["cache_read"] += _integer(
                raw_usage.get("cache_read_input_tokens")
                or raw_usage.get("cached_tokens")
            )
            usage["cache_write"] += _integer(
                raw_usage.get("cache_creation_input_tokens")
                or raw_usage.get("cache_write_tokens")
            )
            usage["output"] += _integer(
                raw_usage.get("output_tokens")
                or raw_usage.get("completion_tokens")
            )
    positions = [event for event in gateway_prefix if event.kind == "position"]
    room_observations = [
        event
        for event in gateway_prefix
        if event.kind == "observation" and event.payload.get("kind") == "room"
    ]
    current_position = positions[-1] if positions else None
    current_room = (
        _text(current_position.payload.get("title"))
        if current_position is not None
        else None
    )
    if current_room is None and room_observations:
        current_room = _text(room_observations[-1].payload.get("title"))
    vitals_event = next(
        (
            event
            for event in reversed(gateway_prefix)
            if event.kind == "observation"
            and event.payload.get("kind") == "vitals"
        ),
        None,
    )
    metric = next(
        (
            event
            for event in reversed(gateway_prefix)
            if event.kind == "parse_metric"
        ),
        None,
    )
    capture_gaps: list[str] = []
    if not agent_events:
        capture_gaps.append("agent_events_missing")
    elif len(agent_events) == 1 and len(gateway_events) > 1:
        capture_gaps.append("agent_events_incomplete")
    if not gateway_events:
        capture_gaps.append("gateway_events_missing")
    if current_room is None:
        capture_gaps.append("position_not_observed")

    return LiveJourneySnapshot(
        session_id=session.id,
        gateway_session_id=session.gateway_session_id,
        player_id=session.player_id,
        character=session.character,
        lifecycle=session.state,
        control_state=session.control_state,
        following_live=through is None or selected == latest,
        through_sequence=selected,
        latest_sequence=latest,
        selected_at=selected_at,
        objective=objective,
        model=_text(session_start.get("model")) if session_start else None,
        tools=tuple(
            tool
            for tool in (
                prompt.get("tools", ()) if prompt is not None else ()
            )
            if isinstance(tool, str)
        ),
        iteration=_integer(iteration.get("n")) if iteration else 0,
        current_room=current_room,
        position_confidence=(
            _text(current_position.payload.get("confidence"))
            if current_position is not None
            else "unknown"
        ) or "unknown",
        position_method=(
            _text(current_position.payload.get("method"))
            if current_position is not None
            else None
        ),
        combat=any(
            event.kind == "observation"
            and (
                event.payload.get("kind") == "combat"
                or event.payload.get("state") == "combat"
            )
            for event in gateway_prefix[-20:]
        ),
        vitals=(
            {
                key: _integer(vitals_event.payload.get(key))
                for key in ("hit", "mana", "move")
            }
            if vitals_event is not None
            else {}
        ),
        cost_usd=round(cost, 8),
        usage=usage,
        parse_miss_rate=(
            _optional_number(metric.payload.get("cumulative_miss_rate"))
            if metric is not None
            else None
        ),
        rooms=_rooms(positions, room_observations),
        timeline=_timeline(gateway_prefix, agent_prefix),
        capture_gaps=tuple(capture_gaps),
    )


def _rooms(
    positions: list[Event],
    observations: list[Event],
) -> tuple[LiveRoom, ...]:
    observation_by_seq = {event.seq: event for event in observations}
    grouped: dict[int, list[Event]] = {}
    for event in positions:
        place = event.payload.get("place")
        if isinstance(place, int):
            grouped.setdefault(place, []).append(event)
    rooms: list[LiveRoom] = []
    current_place = (
        positions[-1].payload.get("place") if positions else None
    )
    for place, events in grouped.items():
        latest = events[-1]
        source = _source_observation(latest, observation_by_seq, observations)
        rooms.append(
            LiveRoom(
                id=f"place-{place}",
                place=place,
                title=_text(latest.payload.get("title")) or f"Place {place}",
                exits=tuple(
                    value
                    for value in (
                        source.payload.get("exits") if source is not None else ()
                    )
                    if isinstance(value, str)
                ),
                first_sequence=events[0].seq,
                last_sequence=events[-1].seq,
                visits=len(events),
                state="current" if place == current_place else "observed",
                confidence=_text(latest.payload.get("confidence")) or "unknown",
            )
        )
    return tuple(sorted(rooms, key=lambda room: room.first_sequence))


def _source_observation(
    position: Event,
    by_sequence: dict[int, Event],
    observations: list[Event],
) -> Event | None:
    wire_ref = position.payload.get("wire_ref")
    if isinstance(wire_ref, dict):
        last = wire_ref.get("last_seq")
        if isinstance(last, int) and last in by_sequence:
            return by_sequence[last]
    return next(
        (
            event
            for event in reversed(observations)
            if event.seq <= position.seq
            and event.payload.get("title") == position.payload.get("title")
        ),
        None,
    )


def _timeline(
    gateway_events: list[Event],
    agent_events: list[dict[str, Any]],
) -> tuple[LiveTimelineItem, ...]:
    gateway_times = [event.at for event in gateway_events]
    items = [
        LiveTimelineItem(
            id=f"gateway-{event.seq}",
            sequence=event.seq,
            at=event.at,
            source="gateway",
            kind=event.kind,
            label=_gateway_label(event),
            trace_id=event.trace_id,
        )
        for event in gateway_events
        if event.kind not in {"wire", "parse_metric", "unparsed"}
    ]
    for event in agent_events:
        phase = _text(event.get("phase"))
        if phase not in {
            "iteration",
            "plan",
            "response",
            "tool_call",
            "tool_result",
            "turn_end",
            "limit_reached",
            "operator_control",
        }:
            continue
        at = _stamp(event.get("at"))
        index = bisect.bisect_right(gateway_times, at)
        sequence = gateway_events[index - 1].seq if index else 0
        items.append(
            LiveTimelineItem(
                id=f"agent-{_integer(event.get('line'))}",
                sequence=sequence,
                at=at,
                source="agent",
                kind=phase,
                label=_agent_label(event),
                cost_usd=_number(event.get("cost_usd")),
                tokens=(
                    _integer(event.get("input_tokens"))
                    + _integer(event.get("output_tokens"))
                ),
                trace_id=None,
            )
        )
    items.sort(key=lambda item: (item.at, item.source, item.id))
    return tuple(items[-80:])


def _objective(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if event.get("phase") != "prompt":
            continue
        messages = event.get("messages")
        if not isinstance(messages, list):
            continue
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, list):
                for block in reversed(content):
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = _text(block.get("text"))
                        if text:
                            return text
    return None


def _latest(
    events: list[dict[str, Any]],
    phase: str,
) -> dict[str, Any] | None:
    return next(
        (event for event in reversed(events) if event.get("phase") == phase),
        None,
    )


def _gateway_label(event: Event) -> str:
    if event.kind == "observation":
        return (
            _text(event.payload.get("title"))
            or _text(event.payload.get("state"))
            or _text(event.payload.get("kind"))
            or "Observation"
        )
    if event.kind == "position":
        title = _text(event.payload.get("title"))
        return f"Position: {title}" if title else "Position unresolved"
    if event.kind == "command":
        line = _text(event.payload.get("line"))
        return f"Command: {line}" if line else "Game command"
    return event.kind.replace("_", " ")


def _agent_label(event: dict[str, Any]) -> str:
    phase = _text(event.get("phase")) or "agent event"
    if phase == "iteration":
        return f"Agent iteration {_integer(event.get('n'))}"
    if phase == "plan":
        return _preview(_text(event.get("text"))) or "Agent plan"
    if phase == "response":
        return f"Model response · {_text(event.get('model')) or 'model'}"
    if phase in {"tool_call", "tool_result"}:
        return f"{phase.replace('_', ' ')} · {_text(event.get('name')) or 'tool'}"
    if phase == "turn_end":
        return f"Turn ended · {_text(event.get('reason')) or 'unknown reason'}"
    if phase == "operator_control":
        action = _text(event.get("action")) or "control"
        instruction = _preview(_text(event.get("instruction")))
        return (
            f"Operator {action}: {instruction}"
            if instruction
            else f"Operator {action}"
        )
    return phase.replace("_", " ")


def _preview(value: str | None, limit: int = 92) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[:limit - 1]}…"


def _stamp(value: Any) -> float:
    if not isinstance(value, str):
        return 0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0


def _optional_number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
