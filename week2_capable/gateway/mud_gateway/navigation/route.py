"""Route planning over the learned graph.

Plain shortest-path search. Edge weights default to hop counts; the
knowledge capability may later supply a weight function without changing
this machinery.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Callable, Iterable

from .graph import Room, WorldGraph

WeightFunction = Callable[[Room, str, str], float]


def _hop(room: Room, direction: str, destination: str) -> float:
    return 1.0


@dataclass(frozen=True)
class RoutePlan:
    """An ordered walk: each step names its direction and expected arrival."""

    steps: tuple[tuple[str, str], ...]

    @property
    def moves(self) -> int:
        return len(self.steps)


def plan_route(
    graph: WorldGraph,
    origin: str,
    destination: str,
    *,
    weight: WeightFunction = _hop,
) -> RoutePlan | None:
    """Cheapest known path between two learned places, or None."""
    if origin == destination:
        return RoutePlan(())
    if origin not in graph.rooms:
        return None
    distances: dict[str, float] = {origin: 0.0}
    parents: dict[str, tuple[str, str]] = {}
    queue: list[tuple[float, str]] = [(0.0, origin)]
    while queue:
        cost, place = heapq.heappop(queue)
        if place == destination:
            break
        if cost > distances.get(place, float("inf")):
            continue
        room = graph.rooms.get(place)
        if room is None:
            continue
        for direction, target in sorted(room.links.items()):
            step = weight(room, direction, target)
            if step == float("inf"):
                continue
            candidate = cost + step
            if candidate < distances.get(target, float("inf")):
                distances[target] = candidate
                parents[target] = (place, direction)
                heapq.heappush(queue, (candidate, target))
    if destination not in parents and origin != destination:
        return None
    steps: list[tuple[str, str]] = []
    cursor = destination
    while cursor != origin:
        place, direction = parents[cursor]
        steps.append((direction, cursor))
        cursor = place
    steps.reverse()
    return RoutePlan(tuple(steps))


def nearest_frontier(
    graph: WorldGraph,
    origin: str,
    searched: Iterable[str] = (),
    *,
    weight: WeightFunction = _hop,
) -> tuple[RoutePlan, str] | None:
    """The cheapest route to a room with unexplored exits, and one exit.

    Returns the route to that room plus the alphabetically first
    unexplored direction, or None when the reachable frontier is empty.
    """
    candidates = {
        room.place_id: room for room in graph.frontier_rooms(searched)
    }
    if not candidates:
        return None
    origin_room = candidates.get(origin)
    if origin_room is not None:
        return RoutePlan(()), sorted(origin_room.frontier())[0]
    best: tuple[float, str, RoutePlan] | None = None
    for place_id in sorted(candidates):
        plan = plan_route(graph, origin, place_id, weight=weight)
        if plan is None:
            continue
        cost = float(plan.moves)
        if best is None or cost < best[0]:
            best = (cost, place_id, plan)
    if best is None:
        return None
    _, place_id, plan = best
    return plan, sorted(candidates[place_id].frontier())[0]
