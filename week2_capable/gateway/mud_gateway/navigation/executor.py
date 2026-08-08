"""Bounded navigation routines executed through the ordinary command path.

Every step is a normal session command, so wire evidence, typed
observations, and knowledge projection happen exactly as they would for a
hand-played move. The model re-enters only through the typed stop reason
each routine returns.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import time

from ..knowledge_models import EvidenceRef
from ..observe import VitalsObservation
from .graph import WorldGraph, canonical_direction
from .route import RoutePlan, nearest_frontier, plan_route

_DIRECTION_WORDS = {
    "north", "south", "east", "west", "up", "down",
}
# Postures a character can walk from. Anything else needs standing first.
_WALKING_POSTURES = {"standing", "fighting"}

# The only two outcomes a sweep continues from, and the two it treats as a
# setback worth retrying elsewhere. Everything else stops it and reports.
#
# Naming what continues rather than what stops is what makes a new outcome
# safe. Listing the stops instead means every new reason has to be added at
# each place an outcome is read, and one that is missed does not stop the
# sweep. That is a hang, not a wrong answer: a step refused on the deadline
# returns without awaiting, so a loop that carries on from it never yields,
# the connection is never read, and the call cannot even be cancelled.
_CARRY_ON = frozenset({"moved", "walked"})
_SETBACKS = frozenset({"blocked_exit", "unexpected_room"})


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
        *,
        call_ceiling: float | None = None,
        clock: Any = None,
    ) -> None:
        block = dict(settings or {})
        self.session = session
        self.store = store
        # A routine has to finish inside the call carrying it, so it stops
        # itself a margin early rather than being cut off with nothing to
        # report. The margin covers the slowest step that can already be
        # walking when the deadline passes.
        self.deadline_margin = float(block.get("deadline_margin", 4.0))
        self.call_ceiling = call_ceiling
        self.clock = clock or time.monotonic
        self.max_rooms = int(block.get("sweep_max_rooms", 30))
        self.max_steps = int(block.get("max_steps", 60))
        self.min_move_points = int(block.get("min_move_points", 15))
        self.max_setbacks = int(block.get("max_setbacks", 3))
        self.travel_enabled = bool(block.get("travel_enabled", True))
        self.ask_where_ways_lead = bool(
            block.get("ask_where_ways_lead", True)
        )
        self.read_new_rooms = bool(block.get("read_new_rooms", True))

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
        known = graph.rooms.get(graph.room_of(current)) if current else None
        linked = set(known.links) if known is not None else set()
        for raw in sorted(live.exits):
            direction = canonical_direction(raw)
            if direction is not None and direction not in linked:
                return direction
        return None

    async def _ensure_standing(self, trace_id: str) -> None:
        """Stand before walking, since a resting character refuses to move.

        The refusal costs a step and reads as a blocked exit, so a routine
        that starts from rest exhausts its setback budget without moving.
        """
        posture = getattr(self.session.observations, "posture", None)
        if posture in _WALKING_POSTURES or posture is None:
            return
        await self.session.command("stand", trace_id=trace_id)

    def _out_of_time(self, state: dict[str, Any]) -> bool:
        """True once too little of the call is left to walk another step."""
        deadline = state.get("deadline")
        return deadline is not None and self.clock() >= deadline

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
        # Asked here rather than at each caller, because this is the one
        # place every walked step passes through. Callers are written and
        # rewritten, and a check they have to remember is a check that
        # eventually goes missing from one of them.
        if self._out_of_time(state):
            return "time_limit"
        await self._ensure_standing(trace_id)
        graph = self._graph()
        origin_place = self._projector.current_place_id
        before = graph.room_of(origin_place)
        live = getattr(self.session.observations, "vitals", None)
        move_before = state.get("move")
        if move_before is None and live is not None:
            move_before = live.move
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
                # Resting is not something a routine can do. The full loop
                # sleeps for minutes against a call measured in seconds,
                # and movement returns on the game's own tick, so a rest
                # cut to fit sits the character down and gains nothing.
                # The model has the command and the time between calls.
                return "needs_rest"
        # Only a move that cost nothing is evidence of a way refusing. When
        # the cost is unknown, nothing is claimed: a wrong "shut door" is
        # remembered forever and steers every later route around a way that
        # was open all along.
        cost_nothing = (
            move_before is not None
            and state.get("move") is not None
            and state["move"] == move_before
        )
        if not reply.position.certain:
            return "position_uncertain"
        after = graph.room_of(self._projector.current_place_id)
        if after is None:
            return "position_unknown"
        if after == before:
            if cost_nothing:
                # A way that refuses costs nothing. Having paid movement and
                # arrived nowhere is something else entirely, an unlit room
                # among them, and must not be remembered as a shut door.
                self._remember_passage(
                    self._projector.current_place_id, direction, "refused",
                    reply,
                )
            return "blocked_exit"
        state["visited"].add(after)
        self._remember_passage(origin_place, direction, "open", reply)
        await self._read_the_room(after, trace_id)
        await self._ask_where_ways_lead(after, trace_id)
        if expected is not None and after != expected:
            return "unexpected_room"
        return "moved"

    def _remember_passage(
        self,
        place: str | None,
        direction: str,
        state: str,
        reply: Any,
    ) -> None:
        """Record whether this way opened, against the place as observed.

        What stopped a refusal takes another action to learn, a shut door,
        a lock, someone barring the way, so only the refusal itself is
        recorded. Walking the same way later records that it opened, which
        replaces the refusal rather than leaving both standing.
        """
        wire = getattr(reply, "wire_ref", None)
        if wire is None or self.store is None or place is None:
            return
        try:
            self.store.assert_fact(
                place,
                f"passage.{direction}",
                state,
                # Whether a way is open is how it stands now, not something
                # learned once. A door shut yesterday and walked today is
                # not a contradiction to keep, it is a newer reading.
                layer="parsed",
                confidence="tracked",
                evidence=EvidenceRef(
                    session_id=wire.source,
                    source_seq=wire.last_seq,
                    wire_digest=wire.digest,
                    parser_version=getattr(reply, "parser_version", "1"),
                    method="movement-refused",
                    observed_at=time.time(),
                ),
            )
        except Exception as error:  # pragma: no cover - instrumentation only
            # Recording what a way did must never end a routine.
            self.session.journal.append(
                self.session.id,
                "passage_note_failed",
                {"place": place, "direction": direction, "error": str(error)},
            )

    async def _read_the_room(self, room: str, trace_id: str) -> None:
        """Read a room's own text the first time, and never again.

        Rooms are told apart by what they say about themselves, so the
        text has to be read once. It never changes after that, and the
        game repeats it on every visit, so it is read on the first arrival
        and skipped once the store holds it.
        """
        if not self.read_new_rooms:
            return
        graph = self._graph()
        known = graph.rooms.get(room)
        if known is not None and getattr(known, "description", None):
            return
        if self._describes(room):
            return
        try:
            await self.session.command("look", trace_id=trace_id)
        except Exception:
            return

    def _describes(self, room: str) -> bool:
        """True when the store already holds this room's own text."""
        if self.store is None:
            return False
        graph = self._graph()
        for fact in self.store.current_facts(layer="learned"):
            if fact.predicate != "description":
                continue
            if graph.room_of(fact.subject) == room and fact.value:
                return True
        return False

    async def _ask_where_ways_lead(self, room: str, trace_id: str) -> None:
        """Ask the game where this room's ways lead, on every arrival.

        One cheap command names the room behind every exit, which beats
        walking each one to find out. It is asked again on every arrival
        rather than remembered, because a door that was shut can be open
        and an answer from an earlier visit would be quietly wrong.
        """
        if not self.ask_where_ways_lead:
            return
        try:
            await self.session.command("exits", trace_id=trace_id)
        except Exception:
            return

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
        deadline = None
        if self.call_ceiling is not None:
            deadline = self.clock() + self.call_ceiling - self.deadline_margin
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
            "deadline": deadline,
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
        try:
            return await self._sweep(state)
        except asyncio.CancelledError:
            # The deadline makes this rare rather than impossible. When it
            # happens the ground covered is still worth recording, and the
            # record is all there is: the library has already answered the
            # call, so nothing reaches the model on this path.
            self._report("sweep", "cancelled", state)
            raise

    async def _sweep(self, state: dict[str, Any]) -> RoutineReport:
        setbacks = 0
        failed_rooms: set[str] = set()
        looked = False
        while True:
            if self._out_of_time(state):
                return self._report("sweep", "time_limit", state)
            if state["steps"] >= self.max_steps:
                return self._report("sweep", "step_limit", state)
            if len(state["visited"]) >= self.max_rooms:
                return self._report("sweep", "room_limit", state)
            current = self._graph().room_of(
                self._projector.current_place_id
            )
            if current is None:
                return self._report("sweep", "position_unknown", state)
            state["visited"].add(current)
            graph = self._graph()
            target = nearest_frontier(graph, current, failed_rooms)
            if target is None and not looked:
                looked = True
                await self.session.command("look", trace_id=state["trace_id"])
                graph = self._graph()
                current = graph.room_of(
                    self._projector.current_place_id
                ) or current
                target = nearest_frontier(graph, current, failed_rooms)
            if target is None:
                direction = self._live_frontier(graph, current)
                if direction is None:
                    return self._report("sweep", "frontier_exhausted", state)
                outcome = await self._step(
                    direction, None, state, state["trace_id"]
                )
                if outcome not in _CARRY_ON and outcome not in _SETBACKS:
                    return self._report("sweep", outcome, state)
                if outcome in _SETBACKS:
                    setbacks += 1
                    if setbacks > self.max_setbacks:
                        return self._report("sweep", "setback_limit", state)
                continue
            plan, direction = target
            frontier_room = (
                plan.steps[-1][1] if plan.steps else current
            )
            walked = await self._walk(plan, state, state["trace_id"])
            if walked not in _CARRY_ON and walked not in _SETBACKS:
                return self._report("sweep", walked, state)
            if walked in _SETBACKS:
                setbacks += 1
                if setbacks > self.max_setbacks:
                    return self._report("sweep", "setback_limit", state)
                continue
            outcome = await self._step(
                direction, None, state, state["trace_id"]
            )
            if outcome not in _CARRY_ON and outcome not in _SETBACKS:
                return self._report("sweep", outcome, state)
            if outcome in _SETBACKS:
                failed_rooms.add(frontier_room)
                setbacks += 1
                if setbacks > self.max_setbacks:
                    return self._report("sweep", "setback_limit", state)

    async def travel(self, destination: str) -> RoutineReport:
        """Walk a computed route to a learned room named by its title."""
        state = self._start("travel", {"destination": destination})
        try:
            return await self._travel(destination, state)
        except asyncio.CancelledError:
            self._report(
                "travel", "cancelled", state, destination=destination
            )
            raise

    async def _travel(
        self, destination: str, state: dict[str, Any]
    ) -> RoutineReport:
        if not self.travel_enabled:
            return self._report(
                "travel", "travel_disabled", state, destination=destination
            )
        current = self._graph().room_of(
            self._projector.current_place_id
        )
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
