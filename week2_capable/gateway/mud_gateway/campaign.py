"""Typed mission readiness for the campaign capability.

One JSON snapshot answering the campaign controller's questions from
facts the agent already earned: has the target been sighted, how healthy
and mobile is the character, what level and gold does it hold, and how
much unexplored ground remains. Matching a sighting against the mission
target compares two pieces of owned data, the same rule that lets travel
match remembered titles.
"""

from __future__ import annotations

import json
from typing import Any

from .navigation.graph import WorldGraph


def mission_readiness(store: Any, target: str) -> dict[str, Any]:
    """Assemble the typed readiness snapshot for one named target."""
    wanted = target.strip().casefold()
    player: dict[str, Any] = {}
    for fact in store.current_facts(layer="parsed"):
        if fact.subject.startswith("player:") \
                and fact.predicate.startswith("state."):
            player[fact.predicate.removeprefix("state.")] = fact.value

    sighted_places: set[str] = set()
    sightings: dict[str, dict[str, Any]] = {}
    for fact in store.current_facts(layer="learned"):
        if not fact.subject.startswith("sighting:"):
            continue
        entry = sightings.setdefault(fact.subject, {})
        entry[fact.predicate] = fact.value
    for entry in sightings.values():
        name = str(entry.get("name", "")).casefold()
        room = entry.get("room")
        if wanted and wanted in name and isinstance(room, str):
            sighted_places.add(room)

    graph = WorldGraph.from_store(store)
    sighted_titles = sorted({
        graph.rooms[place].title
        for place in sighted_places
        if place in graph.rooms and graph.rooms[place].title
    })
    return {
        "target": target,
        "sighted_places": sorted(sighted_places),
        "sighted_titles": sighted_titles,
        "hit": player.get("hit"),
        "max_hit": player.get("max_hit"),
        "move": player.get("move"),
        "max_move": player.get("max_move"),
        "level": player.get("level"),
        "gold": player.get("gold"),
        "rooms_known": len(graph.rooms),
        "frontier_remaining": len(graph.frontier_rooms()),
    }


def readiness_text(report: dict[str, Any]) -> str:
    return json.dumps(report, separators=(",", ":"), sort_keys=True)
