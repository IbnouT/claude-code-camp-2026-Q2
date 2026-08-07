"""The learned world as a graph, read from the knowledge store."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..knowledge import KnowledgeStore

# Stored exits use the game's abbreviations while link facts use the full
# direction words. The graph speaks full words only.
CANONICAL_DIRECTIONS = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "u": "up", "d": "down",
    "north": "north", "south": "south", "east": "east", "west": "west",
    "up": "up", "down": "down",
}


def canonical_direction(direction: str) -> str | None:
    return CANONICAL_DIRECTIONS.get(direction.strip().casefold())


@dataclass
class Room:
    """One learned place: its known exits and where they proved to lead."""

    place_id: str
    title: str = ""
    exits: frozenset[str] = frozenset()
    links: dict[str, str] = field(default_factory=dict)

    def frontier(self) -> frozenset[str]:
        """Exit directions whose far side is unknown."""
        return frozenset(self.exits - self.links.keys())


def _recorded_identity(store: KnowledgeStore) -> dict[str, str]:
    """The place-to-room mapping, empty when identity was never recorded."""
    return {
        fact.subject: fact.value
        for fact in store.current_facts(layer="derived")
        if fact.predicate == "identity.room" and isinstance(fact.value, str)
    }


@dataclass
class WorldGraph:
    """Every learned place, keyed by its stable store identity."""

    rooms: dict[str, Room]

    @classmethod
    def from_store(cls, store: KnowledgeStore) -> "WorldGraph":
        """The map, over rooms when identity was recorded, else over places.

        Identity joins the places one room was seen as, so a route can
        cross a session boundary. Without it every run holds a separate
        copy of the same ground and the map never joins.
        """
        identity = _recorded_identity(store)
        rooms: dict[str, Room] = {}

        def named(place_id: str) -> str:
            return identity.get(place_id, place_id)

        def room(place_id: str) -> Room:
            key = named(place_id)
            return rooms.setdefault(key, Room(key))

        for fact in store.current_facts(layer="learned"):
            if not fact.subject.startswith("place:"):
                continue
            if fact.predicate == "title" and isinstance(fact.value, str):
                room(fact.subject).title = fact.value
            elif fact.predicate == "exits" and isinstance(fact.value, list):
                room(fact.subject).exits = frozenset(
                    canonical for canonical in (
                        canonical_direction(str(direction))
                        for direction in fact.value
                    )
                    if canonical is not None
                )
            elif fact.predicate.startswith("exit.") and isinstance(
                fact.value, str
            ):
                direction = canonical_direction(
                    fact.predicate.removeprefix("exit.")
                )
                if direction is not None:
                    room(fact.subject).links[direction] = named(fact.value)
        return cls(rooms)

    def by_title(self, title: str) -> list[Room]:
        """Learned rooms matching a remembered title.

        Exact matches win. Otherwise any room whose stored title contains
        the requested words is a candidate, so a partial name still finds
        the agent's own memory of the place.
        """
        wanted = title.strip().casefold()
        exact = [
            room for room in self.rooms.values()
            if room.title.strip().casefold() == wanted
        ]
        if exact or not wanted:
            return exact
        return [
            room for room in self.rooms.values()
            if wanted in room.title.strip().casefold()
        ]

    def frontier_rooms(self, searched: Iterable[str] = ()) -> list[Room]:
        """Rooms that still hold unexplored exits, excluding searched ones."""
        excluded = set(searched)
        return [
            room for room in self.rooms.values()
            if room.place_id not in excluded and room.frontier()
        ]
