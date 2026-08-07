"""The learned world as a graph, read from the knowledge store."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

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


_IDENTITY_CACHE: dict[int, dict[str, str]] = {}


def _live_identity(
    store: KnowledgeStore, facts: list[Any]
) -> dict[str, str]:
    """The place-to-room mapping for the facts as they stand right now.

    Identity is computed here rather than read from what was recorded,
    because a place first seen in this run would otherwise belong to no
    room until the run ended, which is precisely when the agent needs to
    know that the room it is standing in is one it has walked before.

    The answer is kept until the store changes, so building the map many
    times in one routine costs one computation.
    """
    from .. import identity as identity_module

    cursor = store.last_change_seq()
    cached = _IDENTITY_CACHE.get(cursor)
    if cached is not None:
        return cached
    bound = {
        binding.place_id: binding.room_id
        for binding in identity_module.resolve(
            identity_module.places_from_facts(facts)
        )
    }
    _IDENTITY_CACHE.clear()
    _IDENTITY_CACHE[cursor] = bound
    return bound


@dataclass
class WorldGraph:
    """Every known room, with the places each was observed as."""

    rooms: dict[str, Room]
    identity: dict[str, str] = field(default_factory=dict)

    def room_of(self, place_id: str | None) -> str | None:
        """The room a place belongs to, or the place when it stands alone."""
        if place_id is None:
            return None
        return self.identity.get(place_id, place_id)

    @classmethod
    def from_store(cls, store: KnowledgeStore) -> "WorldGraph":
        """The map, over rooms when identity was recorded, else over places.

        Identity joins the places one room was seen as, so a route can
        cross a session boundary. Without it every run holds a separate
        copy of the same ground and the map never joins.
        """
        facts = list(store.current_facts(layer="learned"))
        identity = _live_identity(store, facts)
        rooms: dict[str, Room] = {}

        def named(place_id: str) -> str:
            return identity.get(place_id, place_id)

        def room(place_id: str) -> Room:
            key = named(place_id)
            return rooms.setdefault(key, Room(key))

        for fact in facts:
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
        return cls(rooms, dict(identity))

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
