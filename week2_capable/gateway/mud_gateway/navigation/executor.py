"""Bounded navigation routines executed through the ordinary command path.

Every step is a normal session command, so wire evidence, typed
observations, and knowledge projection happen exactly as they would for a
hand-played move. The model re-enters only through the typed stop reason
each routine returns.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from ..observe import VitalsObservation
from .graph import WorldGraph, canonical_direction
from .route import RoutePlan, nearest_frontier, plan_route

_DIRECTION_WORDS = {
    "north", "south", "east", "west", "up", "down",
}


@dataclass(frozen=True)
class RoutineReport:
    """The typed outcome of one bounded routine."""

    routine: str
    stop: str
    steps: int
    rooms_seen: int
    rooms_new: int
    frontier_remaining: int
    move_points: int | None
    destination: str | None = None
    arrived: bool = False

    def text(self) -> str:
        payload: dict[str, Any] = {
            "routine": self.routine,
            "stop": self.stop,
            "steps": self.steps,
            "rooms_seen": self.rooms_seen,
            "rooms_new": self.rooms_new,
            "frontier_remaining": self.frontier_remaining,
        }
        if self.move_points is not None:
            payload["move_points"] = self.move_points
        if self.destination is not None:
            payload["destination"] = self.destination
            payload["arrived"] = self.arrived
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class NavigationExecutor:
    """Sweep and travel over the agent's own learned map."""

    def __init__(
        self,
        session: Any,
        store: Any,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        block = dict(settings or {})
        self.session = session
        self.store = store
        self.max_rooms = int(block.get("sweep_max_rooms", 30))
        self.max_steps = int(block.get("max_steps", 60))
        self.min_move_points = int(block.get("min_move_points", 15))
        self.max_setbacks = int(block.get("max_setbacks", 3))
        self.travel_enabled = bool(block.get("travel_enabled", True))

    # -- shared step machinery ---------------------------------------------

    @property
    def _projector(self) -> Any:
        return self.session.observations.knowledge

    def _graph(self) -> WorldGraph:
        return WorldGraph.from_store(self.store)

    def _live_frontier(
        self,
        graph: WorldGraph,
        current: str | None,
    ) -> str | None:
        """An unexplored exit of the presently observed room, if any.

        The pipeline's retained room observation carries live exits even
        when the store holds nothing for the current place yet, which is
        the state right after a knowledge reset.
        """
        live = getattr(self.session.observations, "room", None)
        if live is None or not live.exits:
            return None
        known = graph.rooms.get(current) if current else None
        linked = set(known.links) if known is not None else set()
        for raw in sorted(live.exits):
            direction = canonical_direction(raw)
            if direction is not None and direction not in linked:
                return direction
        return None

    async def _step(
        self,
        direction: str,
        expected: str | None,
        state: dict[str, Any],
        trace_id: str,
    ) -> str:
        """One walked step. Returns a typed outcome, never prose."""
        if direction not in _DIRECTION_WORDS:
            return "invalid_direction"
        before = self._projector.current_place_id
        reply = await self.session.command(direction, trace_id=trace_id)
        state["steps"] += 1
        vitals = next(
            (
                observation for observation in reply.observations
                if isinstance(observation, VitalsObservation)
            ),
            None,
        )
        if vitals is not None:
            previous_hit = state.get("hit")
            state["hit"] = vitals.hit
            state["move"] = vitals.move
            if previous_hit is not None and vitals.hit < previous_hit:
                return "interrupted"
            if vitals.move < self.min_move_points:
                return "low_vitals"
        if not reply.position.certain:
            return "position_uncertain"
        after = self._projector.current_place_id
        if after is None:
            return "position_unknown"
        if after == before:
            return "blocked_exit"
        state["visited"].add(after)
        if expected is not None and after != expected:
            return "unexpected_room"
        return "moved"

    async def _walk(
        self,
        plan: RoutePlan,
        state: dict[str, Any],
        trace_id: str,
    ) -> str:
        for direction, expected in plan.steps:
            if state["steps"] >= self.max_steps:
                return "step_limit"
            outcome = await self._step(direction, expected, state, trace_id)
            if outcome != "moved":
                return outcome
        return "walked"

    def _report(
        self,
        routine: str,
        stop: str,
        state: dict[str, Any],
        *,
        destination: str | None = None,
        arrived: bool = False,
    ) -> RoutineReport:
        graph = self._graph()
        report = RoutineReport(
            routine=routine,
            stop=stop,
            steps=state["steps"],
            rooms_seen=len(state["visited"]),
            rooms_new=len(
                {
                    place for place in state["visited"]
                    if place not in state["known_at_start"]
                }
            ),
            frontier_remaining=len(graph.frontier_rooms()),
            move_points=state.get("move"),
            destination=destination,
            arrived=arrived,
        )
        self.session.journal.append(
            self.session.id,
            "routine_stop",
            json.loads(report.text()),
            trace_id=state["trace_id"],
        )
        return report

    def _start(self, routine: str, payload: dict[str, Any]) -> dict[str, Any]:
        trace_id = uuid.uuid4().hex
        self.session.journal.append(
            self.session.id,
            "routine_start",
            {"routine": routine, **payload},
            trace_id=trace_id,
        )
        return {
            "steps": 0,
            "visited": set(),
            "known_at_start": frozenset(self._graph().rooms),
            "trace_id": trace_id,
        }

    # -- routines ----------------------------------------------------------

    async def sweep(self) -> RoutineReport:
        """Explore unmapped ground from the learned frontier until bounded."""
        state = self._start(
            "sweep",
            {
                "max_rooms": self.max_rooms,
                "max_steps": self.max_steps,
            },
        )
        setbacks = 0
        failed_rooms: set[str] = set()
        looked = False
        while True:
            if state["steps"] >= self.max_steps:
                return self._report("sweep", "step_limit", state)
            if len(state["visited"]) >= self.max_rooms:
                return self._report("sweep", "room_limit", state)
            current = self._projector.current_place_id
            if current is None:
                return self._report("sweep", "position_unknown", state)
            state["visited"].add(current)
            graph = self._graph()
            target = nearest_frontier(graph, current, failed_rooms)
            if target is None and not looked:
                looked = True
                await self.session.command("look", trace_id=state["trace_id"])
                graph = self._graph()
                current = self._projector.current_place_id or current
                target = nearest_frontier(graph, current, failed_rooms)
            if target is None:
                direction = self._live_frontier(graph, current)
                if direction is None:
                    return self._report("sweep", "frontier_exhausted", state)
                outcome = await self._step(
                    direction, None, state, state["trace_id"]
                )
                if outcome in ("interrupted", "low_vitals",
                               "position_uncertain", "position_unknown"):
                    return self._report("sweep", outcome, state)
                if outcome == "blocked_exit":
                    setbacks += 1
                    if setbacks > self.max_setbacks:
                        return self._report("sweep", "setback_limit", state)
                continue
            plan, direction = target
            frontier_room = (
                plan.steps[-1][1] if plan.steps else current
            )
            walked = await self._walk(plan, state, state["trace_id"])
            if walked in ("interrupted", "low_vitals", "position_uncertain",
                          "position_unknown", "step_limit"):
                return self._report("sweep", walked, state)
            if walked in ("blocked_exit", "unexpected_room"):
                setbacks += 1
                if setbacks > self.max_setbacks:
                    return self._report("sweep", "setback_limit", state)
                continue
            outcome = await self._step(
                direction, None, state, state["trace_id"]
            )
            if outcome in ("interrupted", "low_vitals", "position_uncertain",
                           "position_unknown"):
                return self._report("sweep", outcome, state)
            if outcome == "blocked_exit":
                failed_rooms.add(frontier_room)
                setbacks += 1
                if setbacks > self.max_setbacks:
                    return self._report("sweep", "setback_limit", state)

    async def travel(self, destination: str) -> RoutineReport:
        """Walk a computed route to a learned room named by its title."""
        state = self._start("travel", {"destination": destination})
        if not self.travel_enabled:
            return self._report(
                "travel", "travel_disabled", state, destination=destination
            )
        current = self._projector.current_place_id
        if current is None:
            return self._report(
                "travel", "position_unknown", state, destination=destination
            )
        state["visited"].add(current)
        graph = self._graph()
        matches = graph.by_title(destination)
        if not matches:
            return self._report(
                "travel", "unknown_destination", state,
                destination=destination,
            )
        plans = [
            plan for plan in (
                plan_route(graph, current, room.place_id)
                for room in matches
            )
            if plan is not None
        ]
        if not plans:
            return self._report(
                "travel", "unreachable", state, destination=destination
            )
        plan = min(plans, key=lambda candidate: candidate.moves)
        walked = await self._walk(plan, state, state["trace_id"])
        if walked == "walked":
            return self._report(
                "travel", "arrived", state,
                destination=destination, arrived=True,
            )
        return self._report(
            "travel", walked, state, destination=destination
        )
