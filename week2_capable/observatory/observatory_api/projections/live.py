"""Deterministic Live projection over one runtime session prefix."""

from __future__ import annotations

import bisect
import re
from collections import Counter, deque
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from mud_gateway.journal import Event

from ..contracts import (
    LiveAgentExcerpt,
    LiveCombatEpisode,
    LiveCombatLine,
    LiveEconomicsPoint,
    LiveFrictionDiagnostic,
    LiveJourneySnapshot,
    LiveMilestone,
    LiveOperatorMessage,
    LiveObjectiveContext,
    LiveObservedValue,
    LivePlayerStatus,
    LiveRecentPath,
    LiveRoom,
    LiveRoomEconomics,
    LiveSuggestedAction,
    LiveTimelineItem,
    LiveUnattributedEconomics,
    LiveZoneContext,
    WorldEdge,
    WorldAtlasRoomContext,
    WorldProjection,
)
from ..sources.runtime import RuntimeSession
from .world import project_world_events

if TYPE_CHECKING:
    from ..sources.atlas import AtlasLocation, AtlasSource

_COMBAT_COMMANDS = frozenset(
    {
        "attack",
        "backstab",
        "bash",
        "flee",
        "hit",
        "kick",
        "kill",
        "murder",
    }
)
_PLAYER_DEFEAT = re.compile(
    r"\byou are dead\b|\byou have been killed\b|\bR\.I\.P\b",
    re.I,
)
_DEAD_OPPONENT = re.compile(r"^(?P<opponent>.+?)\s+is dead!", re.I)
_DEATH_CRY = re.compile(r"\bdeath cry\b", re.I)
_PLAYER_FLED = re.compile(r"\byou flee\b|\byou have fled\b", re.I)
_MOB_FLED = re.compile(
    r"\bpanics?, and attempts? to flee\b|\bflees? head over heels\b",
    re.I,
)


def project_live(
    session: RuntimeSession,
    gateway_events: list[Event],
    agent_events: list[dict[str, Any]],
    *,
    through: int | None = None,
    atlas: AtlasSource | None = None,
    operator_messages: list[dict[str, Any]] | None = None,
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
    objective_initial, objective_context = _objective_contexts(agent_prefix)
    agent_thought = _agent_thought(agent_prefix)
    agent_belief = _agent_belief(agent_prefix)
    session_start = _latest(agent_prefix, "session_start")
    iteration = _latest(agent_prefix, "iteration")
    prompt = _latest(agent_prefix, "prompt")
    response_events = [
        event for event in agent_prefix if event.get("phase") == "response"
    ]
    combat_episode = _combat_episode(
        gateway_prefix,
        response_events,
        capture_ended=selected == latest and not session.live,
    )
    turn = len(response_events) or None
    context_limit = _context_limit(agent_prefix)
    economics: list[LiveEconomicsPoint] = []
    usage = {
        "fresh_input": 0,
        "cache_read": 0,
        "cache_write": 0,
        "output": 0,
    }
    cost = 0.0
    for response_number, event in enumerate(response_events, start=1):
        response_cost = _number(event.get("cost_usd"))
        cost += response_cost
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
        economics.append(
            LiveEconomicsPoint(
                response=response_number,
                at=_text(event.get("at")) or "",
                cost_usd=response_cost,
                cumulative_cost_usd=round(cost, 8),
                context_tokens=(
                    _integer(
                        raw_usage.get("input_tokens")
                        or raw_usage.get("prompt_tokens")
                    )
                    + _integer(
                        raw_usage.get("cache_read_input_tokens")
                        or raw_usage.get("cached_tokens")
                    )
                    + _integer(
                        raw_usage.get("cache_creation_input_tokens")
                        or raw_usage.get("cache_write_tokens")
                    )
                    if isinstance(raw_usage, dict)
                    else 0
                ),
            )
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
    world = project_world_events(gateway_prefix, objective=objective)
    zone, atlas_contexts = _atlas_contexts(gateway_prefix, atlas)
    if not atlas_contexts:
        atlas_contexts = _graph_atlas_contexts(world, atlas)
    vitals_event = next(
        (
            event
            for event in reversed(gateway_prefix)
            if event.kind == "observation"
            and event.payload.get("kind") == "vitals"
        ),
        None,
    )
    player_status = _player_status(gateway_prefix, vitals_event)
    spend_cap, spend_scope = _spend_cap(session_start)
    metric = next(
        (
            event
            for event in reversed(gateway_prefix)
            if event.kind == "parse_metric"
        ),
        None,
    )
    if atlas_contexts:
        world = world.model_copy(
            update={
                "nodes": tuple(
                    node.model_copy(
                        update={"atlas": atlas_contexts.get(node.place)}
                    )
                    for node in world.nodes
                )
            }
        )
    room_economics, unattributed_room_economics = _room_economics(
        response_events,
        gateway_prefix,
        world,
    )
    recent_path = _recent_path(gateway_prefix, world)
    suggested_action = _suggested_action(
        world,
        agent_belief,
        expected_sequence=selected,
    )
    milestones = _milestones(gateway_prefix)
    friction = _friction(
        gateway_prefix,
        _integer(iteration.get("n")) if iteration else 0,
        [
            event
            for event in agent_prefix
            if event.get("phase") == "iteration"
        ],
        world,
    )
    timeline = _quiet_cohorts(
        _timeline(gateway_prefix, agent_prefix),
        milestones,
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
    if zone is None:
        capture_gaps.append("zone_not_observed")
    if agent_thought is None:
        capture_gaps.append("agent_thought_not_observed")
    if agent_belief is None:
        capture_gaps.append("agent_belief_not_observed")
    if turn is None:
        capture_gaps.append("turn_not_observed")
    if context_limit is None:
        capture_gaps.append("context_limit_not_observed")

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
        objective_initial=objective_initial,
        objective_context=objective_context,
        suggested_action=suggested_action,
        recent_path=recent_path,
        agent_thought=agent_thought,
        agent_belief=agent_belief,
        model=_text(session_start.get("model")) if session_start else None,
        tools=tuple(
            tool
            for tool in (
                prompt.get("tools", ()) if prompt is not None else ()
            )
            if isinstance(tool, str)
        ),
        turn=turn,
        iteration=_integer(iteration.get("n")) if iteration else 0,
        context_limit=context_limit,
        current_room=current_room,
        zone=zone,
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
        combat=combat_episode.active if combat_episode is not None else False,
        combat_episode=combat_episode,
        friction=friction,
        vitals=(
            {
                key: _integer(vitals_event.payload.get(key))
                for key in ("hit", "mana", "move")
            }
            if vitals_event is not None
            else {}
        ),
        player_status=player_status,
        cost_usd=round(cost, 8),
        current_turn_cost_usd=round(_current_turn_cost(agent_prefix), 8),
        spend_cap_usd=spend_cap,
        spend_cap_scope=spend_scope,
        economics=tuple(economics),
        room_economics=room_economics,
        unattributed_room_economics=unattributed_room_economics,
        usage=usage,
        milestones=milestones,
        parse_miss_rate=(
            _optional_number(metric.payload.get("cumulative_miss_rate"))
            if metric is not None
            else None
        ),
        rooms=_rooms(positions, room_observations),
        world=world,
        timeline=timeline,
        operator_messages=_operator_messages(
            operator_messages or [],
            selected_at=selected_at,
        ),
        capture_gaps=tuple(capture_gaps),
    )


def _operator_messages(
    messages: list[dict[str, Any]],
    *,
    selected_at: float | None,
) -> tuple[LiveOperatorMessage, ...]:
    projected: list[LiveOperatorMessage] = []
    for message in messages:
        sent_at = _text(message.get("sent_at"))
        instruction = _text(message.get("instruction"))
        if sent_at is None or instruction is None:
            continue
        if selected_at is not None and _stamp(sent_at) > selected_at:
            continue
        applied_at = _text(message.get("applied_at"))
        applied_iteration = message.get("applied_iteration")
        applied_in_prefix = (
            isinstance(applied_iteration, int)
            and (
                selected_at is None
                or applied_at is None
                or _stamp(applied_at) <= selected_at
            )
        )
        projected.append(
            LiveOperatorMessage(
                action=(
                    "revise"
                    if message.get("action") == "revise"
                    else "guide"
                ),
                instruction=instruction,
                sent_at=sent_at,
                applied_iteration=(
                    applied_iteration if applied_in_prefix else None
                ),
            )
        )
    return tuple(projected)


def _friction(
    events: list[Event],
    iterations: int,
    iteration_events: list[dict[str, Any]],
    world: WorldProjection,
) -> LiveFrictionDiagnostic:
    positions = [event for event in events if event.kind == "position"]
    iteration_points = sorted(
        (
            _stamp(event.get("at")),
            _integer(event.get("n")),
        )
        for event in iteration_events
        if _stamp(event.get("at")) > 0 and _integer(event.get("n")) > 0
    )
    iteration_times = [point[0] for point in iteration_points]

    def iteration_at(observed_at: float) -> int:
        index = bisect.bisect_right(iteration_times, observed_at)
        return iteration_points[index - 1][1] if index else 0

    first_seen: set[object] = set()
    first_observations: list[tuple[int, int]] = []
    for position in positions:
        place = position.payload.get("place")
        if not isinstance(place, (int, str)) or place in first_seen:
            continue
        first_seen.add(place)
        first_observations.append((iteration_at(position.at), position.seq))

    window_iterations = min(iterations, 10)
    window_start = max(1, iterations - window_iterations + 1)
    new_places = sum(
        1
        for observed_iteration, _ in first_observations
        if observed_iteration >= window_start
    )
    iterations_since_new_place = (
        max(0, iterations - first_observations[-1][0])
        if first_observations
        else None
    )

    command_events = [
        event
        for event in events
        if event.kind == "command"
        and (_text(event.payload.get("line")) or "").strip()
    ]
    current_room_commands: list[Event] = []
    if positions:
        current_place = positions[-1].payload.get("place")
        room_entry_sequence = positions[-1].seq
        for position in reversed(positions[:-1]):
            if position.payload.get("place") != current_place:
                break
            room_entry_sequence = position.seq
        current_room_commands = [
            event
            for event in command_events
            if event.seq > room_entry_sequence
        ]
    counts = Counter(
        (_text(event.payload.get("line")) or "").strip().casefold()
        for event in current_room_commands
    )
    repeated_command: str | None = None
    repeated_count = 0
    if counts:
        repeated_command, repeated_count = counts.most_common(1)[0]
    distinct_places = len(world.nodes)
    kind: Literal["confusion_loop", "progress_stall"] | None = None
    threshold: str | None = None
    evidence: tuple[int, ...] = ()
    if repeated_command is not None and repeated_count >= 5:
        kind = "confusion_loop"
        threshold = "same command recorded at least five times"
        evidence = tuple(
            event.seq
            for event in current_room_commands
            if (_text(event.payload.get("line")) or "").strip().casefold()
            == repeated_command
        )[-5:]
    elif (
        iterations >= 10
        and distinct_places <= max(1, iterations // 10)
    ):
        kind = "progress_stall"
        threshold = "ten or more iterations per distinct observed place"
        evidence = tuple(event.seq for event in positions)[-5:]
    return LiveFrictionDiagnostic(
        kind=kind,
        repeated_command=repeated_command,
        repeated_count=repeated_count,
        distinct_places=distinct_places,
        iterations=iterations,
        new_places=new_places,
        window_iterations=window_iterations,
        iterations_since_new_place=iterations_since_new_place,
        threshold=threshold,
        evidence=evidence,
    )


def _atlas_contexts(
    events: list[Event],
    atlas: AtlasSource | None,
) -> tuple[LiveZoneContext | None, dict[int, WorldAtlasRoomContext]]:
    if atlas is None or not atlas.available:
        return None, {}
    reset = next(
        (
            event
            for event in reversed(events)
            if event.kind == "reset_receipt"
            and event.payload.get("ok") is True
            and isinstance(event.payload.get("verified_room_vnum"), int)
        ),
        None,
    )
    if reset is None:
        return None, {}
    location = atlas.locate(reset.payload["verified_room_vnum"])
    if location is None:
        return None, {}
    commands: dict[str, tuple[str, int]] = {}
    movement_sequences: list[int] = []
    evidence = [f"gateway reset receipt seq {reset.seq}"]
    contexts: dict[int, WorldAtlasRoomContext] = {}
    conflicts: set[int] = set()
    for event in events:
        if event.seq <= reset.seq:
            continue
        if event.kind == "command" and event.trace_id is not None:
            direction = _movement_direction(
                _text(event.payload.get("line")) or ""
            )
            if direction is not None:
                commands[event.trace_id] = (direction, event.seq)
            continue
        if event.kind != "position":
            continue
        command = (
            commands.get(event.trace_id)
            if event.trace_id is not None
            else None
        )
        title = _text(event.payload.get("title"))
        if command is None:
            if title is not None and not _same_title(
                title,
                location.room.title,
            ):
                return None, contexts
            _record_atlas_context(
                contexts,
                conflicts,
                event.payload.get("place"),
                location,
                movement_sequences,
                evidence,
            )
            continue
        direction, command_sequence = command
        target_vnum = location.room.exits.get(direction)
        if target_vnum is None:
            return None, contexts
        target = atlas.locate(target_vnum)
        if (
            target is None
            or title is None
            or not _same_title(title, target.room.title)
        ):
            return None, contexts
        location = target
        movement_sequences.extend((command_sequence, event.seq))
        evidence.append(
            f"gateway movement command seq {command_sequence} "
            f"and position seq {event.seq}"
        )
        _record_atlas_context(
            contexts,
            conflicts,
            event.payload.get("place"),
            location,
            movement_sequences,
            evidence,
        )
    return (
        LiveZoneContext(
            zone_id=location.room.zone,
            label=location.zone_label,
            room_vnum=location.room.vnum,
            sector=location.room.sector,
            form="truth",
            confidence="high" if not movement_sequences else "medium",
            reset_sequence=reset.seq,
            movement_sequences=tuple(movement_sequences),
            atlas_digest=location.source_digest,
            evidence=tuple(evidence),
        ),
        contexts,
    )


def _record_atlas_context(
    contexts: dict[int, WorldAtlasRoomContext],
    conflicts: set[int],
    raw_place: object,
    location: AtlasLocation,
    movement_sequences: list[int],
    evidence: list[str],
) -> None:
    if not isinstance(raw_place, int) or raw_place in conflicts:
        return
    existing = contexts.get(raw_place)
    if existing is not None and existing.vnum != location.room.vnum:
        contexts.pop(raw_place, None)
        conflicts.add(raw_place)
        return
    contexts[raw_place] = WorldAtlasRoomContext(
        vnum=location.room.vnum,
        zone_id=location.room.zone,
        zone_label=location.zone_label,
        sector=location.room.sector,
        atlas_digest=location.source_digest,
        confidence="high" if not movement_sequences else "medium",
        evidence=tuple(evidence),
    )


def _graph_atlas_contexts(
    world: WorldProjection,
    atlas: AtlasSource | None,
) -> dict[int, WorldAtlasRoomContext]:
    """Correlate directional components one atlas step at a time."""

    if atlas is None or not atlas.available or not world.nodes:
        return {}
    nodes = {node.id: node for node in world.nodes}
    edges_by_node: dict[str, list[WorldEdge]] = {
        node_id: [] for node_id in nodes
    }
    for edge in world.edges:
        if _movement_direction(edge.direction) is None:
            continue
        if edge.source not in nodes or edge.target not in nodes:
            continue
        edges_by_node[edge.source].append(edge)
        edges_by_node[edge.target].append(edge)
    for edges in edges_by_node.values():
        edges.sort(key=lambda edge: (edge.evidence[0], edge.id))

    contexts: dict[int, WorldAtlasRoomContext] = {}
    locations: dict[str, AtlasLocation] = {}
    remaining = set(nodes)
    while remaining:
        seed_id = min(
            remaining,
            key=lambda node_id: (
                nodes[node_id].first_seq,
                nodes[node_id].place,
            ),
        )
        component = _directional_component(seed_id, edges_by_node)
        remaining.difference_update(component)
        anchors = [
            (nodes[node_id], location)
            for node_id in component
            if (
                location := atlas.resolve_unique(
                    nodes[node_id].title,
                    nodes[node_id].exits,
                )
            ) is not None
        ]
        if not anchors:
            continue
        anchor, anchor_location = min(
            anchors,
            key=lambda item: (
                -len(item[0].exits),
                item[0].first_seq,
                item[0].place,
            ),
        )
        locations[anchor.id] = anchor_location
        contexts[anchor.place] = _atlas_room_context(
            anchor_location,
            "atlas-unique title and exit anchor",
            confidence="high",
        )
        queue = deque([anchor.id])
        while queue:
            source_id = queue.popleft()
            source_location = locations[source_id]
            for edge in edges_by_node[source_id]:
                if source_id == edge.source:
                    target_id = edge.target
                    direction = _movement_direction(edge.direction)
                else:
                    target_id = edge.source
                    direction = _opposite_direction(edge.direction)
                if direction is None:
                    continue
                target_vnum = source_location.room.exits.get(direction)
                if target_vnum is None:
                    continue
                target_location = atlas.locate(target_vnum)
                target_node = nodes[target_id]
                if (
                    target_location is None
                    or not _same_title(
                        target_node.title,
                        target_location.room.title,
                    )
                    or not _same_exits(
                        target_node.exits,
                        tuple(target_location.room.exits),
                    )
                ):
                    continue
                existing = locations.get(target_id)
                if existing is not None:
                    continue
                locations[target_id] = target_location
                contexts[target_node.place] = _atlas_room_context(
                    target_location,
                    (
                        f"atlas edge {source_location.room.vnum} "
                        f"{direction} to {target_vnum}, "
                        f"gateway edge {edge.id}"
                    ),
                    confidence="medium",
                )
                queue.append(target_id)
    return contexts


def _directional_component(
    seed: str,
    edges_by_node: dict[str, list[WorldEdge]],
) -> set[str]:
    component = {seed}
    queue = deque([seed])
    while queue:
        node_id = queue.popleft()
        for edge in edges_by_node[node_id]:
            adjacent = edge.target if edge.source == node_id else edge.source
            if adjacent in component:
                continue
            component.add(adjacent)
            queue.append(adjacent)
    return component


def _atlas_room_context(
    location: AtlasLocation,
    evidence: str,
    *,
    confidence: Literal["high", "medium"],
) -> WorldAtlasRoomContext:
    return WorldAtlasRoomContext(
        vnum=location.room.vnum,
        zone_id=location.room.zone,
        zone_label=location.zone_label,
        sector=location.room.sector,
        atlas_digest=location.source_digest,
        confidence=confidence,
        evidence=(evidence,),
    )


def _opposite_direction(direction: str) -> str | None:
    normalized = _movement_direction(direction)
    return {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "up": "down",
        "down": "up",
    }.get(normalized or "")


def _same_exits(observed: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    normalized = {
        _movement_direction(direction) or direction.casefold()
        for direction in observed
    }
    return normalized == set(expected)


def _suggested_action(
    world: WorldProjection,
    belief: LiveAgentExcerpt | None,
    *,
    expected_sequence: int,
) -> LiveSuggestedAction | None:
    current = next(
        (node for node in world.nodes if node.state == "current"),
        None,
    )
    if current is not None:
        routes = [
            (
                route,
                beacon,
            )
            for beacon in world.objective_beacons
            if (
                route := _route_to(
                    current.id,
                    beacon.node_id,
                    world.edges,
                )
            )
        ]
        if routes:
            route, beacon = min(
                routes,
                key=lambda item: (
                    len(item[0]),
                    item[1].evidence[0] if item[1].evidence else 0,
                    item[1].node_id,
                ),
            )
            directions = ", ".join(edge.direction for edge in route)
            route_evidence = tuple(
                f"gateway transition seq {sequence}"
                for edge in route
                for sequence in edge.evidence
            )
            beacon_evidence = tuple(
                f"objective beacon seq {sequence}"
                for sequence in beacon.evidence
            )
            return LiveSuggestedAction(
                kind="route",
                label=f"Head to {beacon.label}",
                instruction=(
                    f"Follow the learned route toward {beacon.label}: "
                    f"{directions}."
                ),
                reason=(
                    f"A retained objective sighting at {beacon.node_id} "
                    f"is reachable by {len(route)} learned transition"
                    f"{'' if len(route) == 1 else 's'}."
                ),
                evidence=(*beacon_evidence, *route_evidence),
                expected_sequence=expected_sequence,
            )
    if belief is None:
        return None
    return LiveSuggestedAction(
        kind="continue_plan",
        label=f"Continue: {belief.text}",
        instruction=f"Continue the retained intended action: {belief.text}.",
        reason="The selected agent's latest retained tool intent supports it.",
        evidence=(belief.evidence,),
        expected_sequence=expected_sequence,
    )


def _recent_path(
    events: list[Event],
    world: WorldProjection,
    *,
    limit: int = 3,
) -> LiveRecentPath | None:
    edge_by_transition = {
        (
            int(edge.source.removeprefix("place:")),
            int(edge.target.removeprefix("place:")),
            sequence,
        ): edge
        for edge in world.edges
        for sequence in edge.evidence
    }
    transitions: list[tuple[int, int, WorldEdge, int]] = []
    previous: int | None = None
    for event in events:
        if event.kind != "position":
            continue
        place = event.payload.get("place")
        if not isinstance(place, int):
            transitions.clear()
            previous = None
            continue
        if previous is not None and place != previous:
            edge = edge_by_transition.get((previous, place, event.seq))
            if edge is None or edge.direction == "unknown":
                transitions.clear()
            else:
                transitions.append((previous, place, edge, event.seq))
        previous = place
    if previous is None or not transitions:
        return None
    selected: list[tuple[WorldEdge, int]] = []
    expected_target = previous
    for source, target, edge, sequence in reversed(transitions):
        if target != expected_target:
            break
        selected.append((edge, sequence))
        expected_target = source
        if len(selected) == limit:
            break
    if not selected:
        return None
    selected.reverse()
    return LiveRecentPath(
        edge_ids=tuple(edge.id for edge, _ in selected),
        gateway_sequences=tuple(sequence for _, sequence in selected),
    )


def _route_to(
    source: str,
    target: str,
    edges: tuple[WorldEdge, ...],
) -> tuple[WorldEdge, ...]:
    if source == target:
        return ()
    outgoing: dict[str, list[WorldEdge]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source, []).append(edge)
    queue = deque([(source, ())])
    visited = {source}
    while queue:
        node, route = queue.popleft()
        for edge in sorted(
            outgoing.get(node, ()),
            key=lambda item: (item.direction, item.target, item.id),
        ):
            if edge.target in visited:
                continue
            next_route = (*route, edge)
            if edge.target == target:
                return next_route
            visited.add(edge.target)
            queue.append((edge.target, next_route))
    return ()


def _movement_direction(line: str) -> str | None:
    directions = {
        "n": "north",
        "north": "north",
        "e": "east",
        "east": "east",
        "s": "south",
        "south": "south",
        "w": "west",
        "west": "west",
        "u": "up",
        "up": "up",
        "d": "down",
        "down": "down",
    }
    return directions.get(line.strip().casefold())


def _same_title(left: str, right: str) -> bool:
    return " ".join(left.casefold().split()) == " ".join(
        right.casefold().split()
    )


def _combat_episode(
    gateway_events: list[Event],
    response_events: list[dict[str, Any]],
    *,
    capture_ended: bool,
) -> LiveCombatEpisode | None:
    """Port the Week 0 command-plus-response episode onto retained evidence."""

    combat_traces = {
        event.trace_id
        for event in gateway_events
        if event.trace_id
        and event.kind == "observation"
        and event.payload.get("kind") == "combat"
    }
    command_by_trace: dict[str, tuple[str, str | None, int]] = {}
    episode: dict[str, Any] | None = None

    for event in gateway_events:
        if event.kind == "command":
            line = _text(event.payload.get("line")) or ""
            verb, target = _combat_command(line)
            if event.trace_id:
                command_by_trace[event.trace_id] = (
                    verb,
                    target,
                    event.seq,
                )
            if (
                episode is not None
                and episode["active"]
                and verb not in _COMBAT_COMMANDS
                and event.trace_id not in combat_traces
            ):
                episode["active"] = False
                episode["outcome"] = episode["outcome"] or "ended"
                episode["evidence"].append(event.seq)
            continue

        if event.kind != "observation":
            continue

        text = _text(event.payload.get("text")) or ""
        observation_kind = event.payload.get("kind")
        if observation_kind == "combat":
            command = (
                command_by_trace.get(event.trace_id)
                if event.trace_id is not None
                else None
            )
            combat_command = (
                command
                if command is not None and command[0] in _COMBAT_COMMANDS
                else None
            )
            target = combat_command[1] if combat_command is not None else None
            switched = (
                episode is not None
                and episode["active"]
                and target is not None
                and episode["opponent"] is not None
                and _normalise_opponent(target)
                != _normalise_opponent(episode["opponent"])
            )
            if switched:
                episode["active"] = False
                episode["outcome"] = "ended"
                episode["evidence"].append(combat_command[2])
            elif (
                episode is not None
                and episode["active"]
                and episode["opponent"] is None
                and combat_command is not None
                and target is not None
            ):
                episode["opponent"] = target
                episode["command_trace"] = event.trace_id
                episode["evidence"].append(combat_command[2])
            if episode is None or not episode["active"]:
                command_sequence = (
                    combat_command[2]
                    if combat_command is not None
                    else None
                )
                evidence = (
                    [command_sequence, event.seq]
                    if command_sequence is not None
                    else [event.seq]
                )
                episode = {
                    "active": True,
                    "opponent": target,
                    "first_observed_turn": _turn_at(
                        response_events,
                        event.at,
                    ),
                    "outcome": None,
                    "command_trace": (
                        event.trace_id
                        if combat_command is not None
                        else None
                    ),
                    "lines": [],
                    "evidence": evidence,
                }
            if text:
                episode["lines"].append(
                    LiveCombatLine(
                        text=text,
                        sequence=event.seq,
                        observed_at=event.at,
                        confidence=(
                            _text(event.payload.get("confidence")) or "unknown"
                        ),
                        method=(
                            _text(event.payload.get("method")) or "unknown"
                        ),
                        evidence=f"gateway observation seq {event.seq}",
                    )
                )
            episode["lines"] = episode["lines"][-25:]
            episode["evidence"].append(event.seq)

        if episode is None or not episode["active"] or not text:
            continue
        if observation_kind == "death" or _PLAYER_DEFEAT.search(text):
            _end_combat(episode, "defeated", event.seq)
        elif _PLAYER_FLED.search(text) or _MOB_FLED.search(text):
            _end_combat(episode, "fled", event.seq)
        elif _death_matches_opponent(text, episode["opponent"]):
            _end_combat(episode, "victory", event.seq)
        elif episode["opponent"] is None and _DEATH_CRY.search(text):
            _end_combat(episode, "victory", event.seq)

    if episode is not None and episode["active"] and capture_ended:
        episode["active"] = False
        episode["outcome"] = "unresolved"
        if gateway_events:
            episode["evidence"].append(gateway_events[-1].seq)

    if episode is None:
        return None
    return LiveCombatEpisode(
        active=episode["active"],
        opponent=episode["opponent"],
        first_observed_turn=episode["first_observed_turn"],
        observed_exchanges=len(episode["lines"]),
        outcome=episode["outcome"],
        command_trace=episode["command_trace"],
        lines=tuple(episode["lines"]),
        evidence=tuple(dict.fromkeys(episode["evidence"])),
    )


def _end_combat(
    episode: dict[str, Any],
    outcome: Literal[
        "victory",
        "defeated",
        "fled",
        "ended",
        "unresolved",
    ],
    sequence: int,
) -> None:
    episode["active"] = False
    episode["outcome"] = outcome
    episode["evidence"].append(sequence)


def _death_matches_opponent(text: str, opponent: str | None) -> bool:
    match = _DEAD_OPPONENT.search(text)
    if match is None:
        return False
    if opponent is None:
        return True
    observed = _normalise_opponent(match.group("opponent"))
    expected = _normalise_opponent(opponent)
    return (
        expected == observed
        or _contains_words(observed, expected)
        or _contains_words(expected, observed)
    )


def _normalise_opponent(value: str) -> str:
    words = value.casefold().strip(" .!").split()
    if words and words[0] in {"a", "an", "the"}:
        words = words[1:]
    return " ".join(words)


def _contains_words(value: str, candidate: str) -> bool:
    words = value.split()
    candidate_words = candidate.split()
    size = len(candidate_words)
    if size == 0 or size > len(words):
        return False
    return any(
        words[index:index + size] == candidate_words
        for index in range(len(words) - size + 1)
    )


def _combat_command(line: str) -> tuple[str, str | None]:
    parts = line.strip().split(maxsplit=1)
    if not parts:
        return "", None
    verb = parts[0].casefold()
    target = parts[1].strip() if len(parts) == 2 else None
    return verb, target if verb in _COMBAT_COMMANDS and target else None


def _turn_at(
    response_events: list[dict[str, Any]],
    observed_at: float,
) -> int | None:
    count = sum(
        1
        for event in response_events
        if 0 < _stamp(event.get("at")) <= observed_at
    )
    return count or None


def _player_status(
    events: list[Event],
    vitals_event: Event | None,
) -> LivePlayerStatus:
    fields: dict[str, LiveObservedValue] = {}
    for event in events:
        if (
            event.kind != "observation"
            or event.payload.get("kind") != "player_state"
        ):
            continue
        values = event.payload.get("values")
        if not isinstance(values, dict):
            continue
        for name, value in values.items():
            if not isinstance(name, str) or not isinstance(
                value,
                (bool, int, str),
            ):
                continue
            fields[name] = LiveObservedValue(
                value=value,
                sequence=event.seq,
                observed_at=event.at,
                confidence=_text(event.payload.get("confidence")) or "unknown",
                method=_text(event.payload.get("method")) or "unknown",
            )
    if vitals_event is not None:
        for name in ("hit", "mana", "move"):
            if name in fields:
                continue
            value = vitals_event.payload.get(name)
            if isinstance(value, int):
                fields[name] = LiveObservedValue(
                    value=value,
                    sequence=vitals_event.seq,
                    observed_at=vitals_event.at,
                    confidence=(
                        _text(vitals_event.payload.get("confidence"))
                        or "unknown"
                    ),
                    method=_text(vitals_event.payload.get("method")) or "unknown",
                )
    expected = (
        "hit",
        "mana",
        "move",
        "level",
        "gold",
        "posture",
        "hungry",
        "thirsty",
        "drunk",
        "poisoned",
    )
    return LivePlayerStatus(
        fields=fields,
        capture_gaps=tuple(name for name in expected if name not in fields),
    )


def _spend_cap(
    session_start: dict[str, Any] | None,
) -> tuple[float | None, Literal["session", "turn"] | None]:
    if session_start is None:
        return None, None
    for name in ("max_total_cost_usd", "max_session_cost"):
        value = _optional_number(session_start.get(name))
        if value is not None and value > 0:
            return value, "session"
    value = _optional_number(session_start.get("max_turn_cost"))
    if value is not None and value > 0:
        return value, "turn"
    return None, None


def _current_turn_cost(events: list[dict[str, Any]]) -> float:
    start = max(
        (
            index
            for index, event in enumerate(events)
            if event.get("phase") == "turn"
        ),
        default=0,
    )
    return sum(
        _number(event.get("cost_usd"))
        for event in events[start:]
        if event.get("phase") == "response"
    )


def _room_economics(
    responses: list[dict[str, Any]],
    gateway_events: list[Event],
    world: WorldProjection,
) -> tuple[
    tuple[LiveRoomEconomics, ...],
    LiveUnattributedEconomics | None,
]:
    if not responses:
        return (), None
    known_nodes = {node.place: node.id for node in world.nodes}
    positions = [
        event for event in gateway_events if event.kind == "position"
    ]
    attributed: dict[str, dict[str, Any]] = {}
    unattributed_evidence: list[str] = []
    unattributed_cost = 0.0
    for response_number, response in enumerate(responses, start=1):
        stamp = _stamp(response.get("at"))
        evidence = _agent_response_evidence(response, response_number)
        latest_position = next(
            (
                event
                for event in reversed(positions)
                if stamp > 0 and event.at <= stamp
            ),
            None,
        )
        place = (
            latest_position.payload.get("place")
            if latest_position is not None
            else None
        )
        confidence = (
            _text(latest_position.payload.get("confidence"))
            if latest_position is not None
            else None
        )
        node_id = (
            known_nodes.get(place)
            if isinstance(place, int)
            and confidence not in {"ambiguous", "unknown"}
            else None
        )
        cost = _number(response.get("cost_usd"))
        if node_id is None or latest_position is None:
            unattributed_cost += cost
            unattributed_evidence.append(evidence)
            continue
        item = attributed.setdefault(
            node_id,
            {
                "responses": [],
                "cost_usd": 0.0,
                "evidence": [],
            },
        )
        item["responses"].append(response_number)
        item["cost_usd"] += cost
        item["evidence"].append(
            f"{evidence}; gateway position seq {latest_position.seq}"
        )
    room_items = tuple(
        LiveRoomEconomics(
            node_id=node_id,
            response_count=len(item["responses"]),
            cost_usd=round(item["cost_usd"], 8),
            first_response=int(item["responses"][0]),
            last_response=int(item["responses"][-1]),
            evidence=tuple(item["evidence"]),
        )
        for node_id, item in sorted(
            attributed.items(),
            key=lambda entry: int(entry[1]["responses"][0]),
        )
    )
    return (
        room_items,
        LiveUnattributedEconomics(
            response_count=len(unattributed_evidence),
            cost_usd=round(unattributed_cost, 8),
            evidence=tuple(unattributed_evidence),
        ),
    )


def _agent_response_evidence(
    response: dict[str, Any],
    response_number: int,
) -> str:
    line = response.get("line")
    if isinstance(line, int) and line > 0:
        return f"agent log line {line}"
    at = _text(response.get("at"))
    return (
        f"agent response {response_number} at {at}"
        if at is not None
        else f"agent response {response_number} with missing timestamp"
    )


def _context_limit(events: list[dict[str, Any]]) -> int | None:
    for event in reversed(events):
        value = event.get("context_window")
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None


def _milestones(events: list[Event]) -> tuple[LiveMilestone, ...]:
    previous: int | None = None
    milestones: list[LiveMilestone] = []
    for event in events:
        if (
            event.kind != "observation"
            or event.payload.get("kind") != "player_state"
        ):
            continue
        values = event.payload.get("values")
        level = values.get("level") if isinstance(values, dict) else None
        if not isinstance(level, int):
            continue
        if previous is not None and level > previous:
            milestones.append(
                LiveMilestone(
                    kind="level_up",
                    sequence=event.seq,
                    at=event.at,
                    previous=previous,
                    current=level,
                    evidence=f"gateway observation seq {event.seq}",
                )
            )
        previous = level
    return tuple(milestones)


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
        if phase == "operator_control" and gateway_events:
            index = min(
                bisect.bisect_left(gateway_times, at),
                len(gateway_events) - 1,
            )
            sequence = gateway_events[index].seq
        else:
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


def _quiet_cohorts(
    timeline: tuple[LiveTimelineItem, ...],
    milestones: tuple[LiveMilestone, ...],
) -> tuple[LiveTimelineItem, ...]:
    """Tag contiguous minor activity runs between retained landmarks."""
    if not timeline:
        return ()

    landmark_ids: set[str] = set()
    room = next(
        (
            item
            for item in timeline
            if "position" in item.kind.lower() or "room" in item.kind.lower()
        ),
        None,
    )
    if room is not None:
        landmark_ids.add(room.id)

    milestone = milestones[-1] if milestones else None
    milestone_sequence = milestone.sequence if milestone is not None else None
    if milestone_sequence is not None:
        landmark_ids.update(
            item.id for item in timeline if item.sequence == milestone_sequence
        )

    combat = [
        item for item in timeline if "combat" in item.kind.lower()
    ]
    if combat:
        landmark_ids.add(combat[0].id)
        landmark_ids.add(combat[-1].id)

    landmark_ids.update(
        item.id
        for item in timeline
        if "control" in item.kind.lower() or "operator" in item.kind.lower()
    )

    cohort_number = 0
    active_category: tuple[str, str] | None = None
    tagged: list[LiveTimelineItem] = []
    for item in timeline:
        if item.id in landmark_ids:
            active_category = None
            tagged.append(item)
            continue
        category = (item.source, item.kind.lower())
        if category != active_category:
            cohort_number += 1
            active_category = category
        tagged.append(
            item.model_copy(
                update={"quiet_cohort": f"quiet-{cohort_number}"}
            )
        )
    return tuple(tagged)


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
                        if (
                            text
                            and not text.startswith(
                                "Authenticated operator guidance for the "
                                "active objective:"
                            )
                        ):
                            return text
    return None


def _objective_contexts(
    events: list[dict[str, Any]],
) -> tuple[LiveObjectiveContext | None, LiveObjectiveContext | None]:
    initial: LiveObjectiveContext | None = None
    current: LiveObjectiveContext | None = None
    for event in events:
        if event.get("phase") == "session_start":
            value = event.get("objective")
            if not isinstance(value, dict):
                continue
            title = _text(value.get("title"))
            source_kind = value.get("source_kind")
            revision = value.get("revision")
            if (
                title is None
                or source_kind not in {"benchmark", "operator"}
                or not isinstance(revision, int)
                or revision < 1
            ):
                continue
            line = _integer(event.get("line"))
            authored = LiveObjectiveContext(
                title=title,
                clue=_text(value.get("clue")),
                source_kind=source_kind,
                revision=revision,
                evidence=f"agent log line {line}",
            )
            if initial is None:
                initial = authored
            current = authored
            continue
        if (
            event.get("phase") != "operator_control"
            or event.get("action") != "revise"
        ):
            continue
        instruction = _text(event.get("instruction"))
        if instruction is None or not instruction.strip():
            continue
        line = _integer(event.get("line"))
        current = LiveObjectiveContext(
            title=instruction.strip(),
            clue=None,
            source_kind="operator",
            revision=(current.revision + 1 if current is not None else 1),
            evidence=f"agent log line {line}",
        )
    return initial, current


def _agent_thought(
    events: list[dict[str, Any]],
) -> LiveAgentExcerpt | None:
    for event in reversed(events):
        phase = _text(event.get("phase"))
        if phase not in {"reasoning", "plan"}:
            continue
        if phase == "reasoning" and event.get("redacted") is True:
            continue
        text = _text(event.get("text"))
        if text is None or not text.strip():
            continue
        return _agent_excerpt(event, phase, text.strip())
    return None


def _agent_belief(
    events: list[dict[str, Any]],
) -> LiveAgentExcerpt | None:
    for event in reversed(events):
        if event.get("phase") != "tool_call":
            continue
        name = _text(event.get("name"))
        if name is None:
            continue
        args = event.get("args")
        values = args if isinstance(args, dict) else {}
        bare_name = name.rsplit("__", maxsplit=1)[-1]
        if bare_name == "move":
            direction = _text(values.get("direction"))
            text = f"Moving {direction}" if direction else "Moving"
        elif bare_name in {"attack", "kill"}:
            target = _text(values.get("target"))
            text = f"Attacking {target}" if target else "Attacking"
        elif bare_name == "look":
            target = _text(values.get("target"))
            text = f"Looking at {target}" if target else "Looking around"
        else:
            text = f"Using {bare_name.replace('_', ' ')}"
        return _agent_excerpt(event, "tool_call", text)
    return None


def _agent_excerpt(
    event: dict[str, Any],
    phase: Literal["reasoning", "plan", "tool_call"],
    text: str,
) -> LiveAgentExcerpt:
    line = _integer(event.get("line"))
    return LiveAgentExcerpt(
        text=text,
        phase=phase,
        observed_at=_text(event.get("at")) or "",
        line=line,
        evidence=f"agent log line {line}",
    )


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
