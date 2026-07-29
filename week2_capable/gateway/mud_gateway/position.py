"""Conservative position inference from traceable room observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .observe import (
    PARSER_VERSION,
    Observation,
    RoomObservation,
    StateObservation,
    WireReference,
)

OPPOSITE = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "down",
    "down": "up",
    "n": "s",
    "s": "n",
    "e": "w",
    "w": "e",
    "u": "d",
    "d": "u",
}


class PositionConfidence(str, Enum):
    CONFIRMED = "confirmed"
    TRACKED = "tracked"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass
class Place:
    key: int
    title: str
    exits: tuple[str, ...]
    neighbours: dict[str, int] = field(default_factory=dict)

    def signature(self) -> tuple[str, tuple[str, ...]]:
        return self.title.casefold(), tuple(sorted(self.exits))


@dataclass(frozen=True)
class PositionObservation:
    place: int | None
    title: str | None
    confidence: PositionConfidence
    method: str
    wire_ref: WireReference
    parser_version: str = PARSER_VERSION

    @property
    def certain(self) -> bool:
        return self.confidence in {
            PositionConfidence.CONFIRMED,
            PositionConfidence.TRACKED,
        }

    def payload(self) -> dict[str, object]:
        return {
            "place": self.place,
            "title": self.title,
            "confidence": self.confidence.value,
            "method": self.method,
            "parser_version": self.parser_version,
            "wire_ref": {
                "source": self.wire_ref.source,
                "first_seq": self.wire_ref.first_seq,
                "last_seq": self.wire_ref.last_seq,
                "digest": self.wire_ref.digest,
            },
        }


class PositionTracker:
    """Resolve by arrival path and title plus exits, never by title alone."""

    def __init__(self) -> None:
        self.places: dict[int, Place] = {}
        self._by_title: dict[str, list[int]] = {}
        self._next = 1
        self._pending_move: str | None = None
        empty_ref = WireReference("none", 0, 0, "0" * 32)
        self.position = PositionObservation(
            None,
            None,
            PositionConfidence.UNKNOWN,
            "nothing-observed",
            empty_ref,
        )

    def moving(self, direction: str) -> None:
        self._pending_move = direction.casefold()

    def observe(self, observations: list[Observation]) -> PositionObservation:
        for observation in observations:
            if isinstance(observation, StateObservation):
                if observation.kind == "death":
                    self._pending_move = None
                    self.position = PositionObservation(
                        None,
                        None,
                        PositionConfidence.UNKNOWN,
                        "game-relocated-character",
                        observation.wire_ref,
                    )
                elif observation.kind in {"refused", "door"} and self._pending_move:
                    self._pending_move = None
                    self.position = PositionObservation(
                        self.position.place,
                        self.position.title,
                        self.position.confidence,
                        "move-did-not-happen",
                        observation.wire_ref,
                    )
                elif observation.kind == "dark":
                    self._pending_move = None
                    self.position = PositionObservation(
                        None,
                        None,
                        PositionConfidence.AMBIGUOUS,
                        "room-unlit",
                        observation.wire_ref,
                    )
            if isinstance(observation, RoomObservation):
                self.position = self._arrive(observation)
                self._pending_move = None
        return self.position

    def _arrive(self, room: RoomObservation) -> PositionObservation:
        title = room.title
        exits = tuple(room.exits)
        candidates = self._by_title.get(title.casefold(), [])

        if self._pending_move and self.position.place is not None:
            current = self.places[self.position.place]
            target = current.neighbours.get(self._pending_move)
            if target is not None:
                place = self.places[target]
                if place.signature() == (title.casefold(), tuple(sorted(exits))):
                    return PositionObservation(
                        target,
                        title,
                        PositionConfidence.TRACKED,
                        "known-neighbour+matching-signature",
                        room.wire_ref,
                    )

            matching_neighbours = [
                key
                for key in candidates
                if self.places[key].signature()
                == (title.casefold(), tuple(sorted(exits)))
                and self.places[key].neighbours.get(OPPOSITE.get(self._pending_move, ""))
                == current.key
            ]
            if len(matching_neighbours) == 1:
                key = matching_neighbours[0]
                self._link_from_previous(key)
                return PositionObservation(
                    key,
                    title,
                    PositionConfidence.TRACKED,
                    "matching-signature+neighbourhood",
                    room.wire_ref,
                )

            key = self._add(title, exits)
            self._link_from_previous(key)
            return PositionObservation(
                key,
                title,
                PositionConfidence.TRACKED,
                "new-arrival-path",
                room.wire_ref,
            )

        signature = (title.casefold(), tuple(sorted(exits)))
        matching = [key for key in candidates if self.places[key].signature() == signature]
        if len(matching) == 1:
            key = matching[0]
            self._link_from_previous(key)
            return PositionObservation(
                key,
                title,
                PositionConfidence.CONFIRMED,
                "unique-title+exits",
                room.wire_ref,
            )

        if not candidates:
            key = self._add(title, exits)
            self._link_from_previous(key)
            return PositionObservation(
                key,
                title,
                PositionConfidence.TRACKED,
                "new-title",
                room.wire_ref,
            )

        if len(matching) > 1 or not exits:
            return PositionObservation(
                None,
                title,
                PositionConfidence.AMBIGUOUS,
                "duplicate-title-not-separated",
                room.wire_ref,
            )

        key = self._add(title, exits)
        self._link_from_previous(key)
        return PositionObservation(
            key,
            title,
            PositionConfidence.TRACKED,
            "duplicate-title+new-exits",
            room.wire_ref,
        )

    def _add(self, title: str, exits: tuple[str, ...]) -> int:
        key = self._next
        self._next += 1
        self.places[key] = Place(key, title, exits)
        self._by_title.setdefault(title.casefold(), []).append(key)
        return key

    def _link_from_previous(self, target: int) -> None:
        if self._pending_move and self.position.place is not None:
            source = self.position.place
            self.places[source].neighbours[self._pending_move] = target
            back = OPPOSITE.get(self._pending_move)
            if back:
                self.places[target].neighbours.setdefault(back, source)
