from __future__ import annotations

from mud_gateway.observe import WireReference, parse
from mud_gateway.position import (
    PositionConfidence,
    PositionObservation,
    PositionTracker,
)

WIRE = WireReference("recording", 1, 1, "b" * 32)
ROOM_A = (
    "\x1b[0;33mThe Temple\x1b[0m\r\n"
    "\x1b[0;36m[ Exits: n s ]\x1b[0m\r\n20H 100M 82V > "
)
ROOM_B = (
    "\x1b[0;33mMain Street\x1b[0m\r\n"
    "\x1b[0;36m[ Exits: e w ]\x1b[0m\r\n20H 100M 82V > "
)
ROOM_B_TWIN = (
    "\x1b[0;33mMain Street\x1b[0m\r\n"
    "\x1b[0;36m[ Exits: n s ]\x1b[0m\r\n20H 100M 82V > "
)


def walk(tracker: PositionTracker, room: str, direction: str | None = None):
    if direction:
        tracker.moving(direction)
    return tracker.observe(parse(room, WIRE))


def test_known_neighbour_and_signature_restore_the_same_place():
    tracker = PositionTracker()
    start = walk(tracker, ROOM_A).place
    walk(tracker, ROOM_B, "north")
    back = walk(tracker, ROOM_A, "south")
    assert back.place == start
    assert back.certain


def test_same_title_with_different_exits_never_collapses():
    tracker = PositionTracker()
    first = walk(tracker, ROOM_B).place
    tracker.position = PositionObservation(
        None,
        None,
        PositionConfidence.UNKNOWN,
        "reconnected",
        WIRE,
    )
    second = walk(tracker, ROOM_B_TWIN).place
    assert first != second
    assert len(tracker.places) == 2


def test_same_title_and_exits_from_a_new_neighbourhood_never_collapses():
    tracker = PositionTracker()
    first = walk(tracker, ROOM_B).place
    walk(tracker, ROOM_A, "east")
    second = walk(tracker, ROOM_B, "north").place
    assert first != second
    assert len(tracker.places) == 3


def test_duplicate_title_and_signature_from_unknown_is_ambiguous():
    tracker = PositionTracker()
    walk(tracker, ROOM_B)
    tracker._add("Main Street", ("e", "w"))
    tracker.position = PositionObservation(
        None,
        None,
        PositionConfidence.UNKNOWN,
        "reconnected",
        WIRE,
    )
    position = walk(tracker, ROOM_B)
    assert position.confidence is PositionConfidence.AMBIGUOUS
    assert position.place is None


def test_refused_move_does_not_advance_position():
    tracker = PositionTracker()
    before = walk(tracker, ROOM_A)
    tracker.moving("north")
    after = tracker.observe(parse("Alas, you cannot go that way...\r\n", WIRE))
    assert after.place == before.place
    assert after.method == "move-did-not-happen"


def test_darkness_and_death_lower_confidence_instead_of_guessing():
    tracker = PositionTracker()
    walk(tracker, ROOM_A)
    tracker.moving("north")
    dark = tracker.observe(parse("It is pitch black...\r\n", WIRE))
    assert dark.confidence is PositionConfidence.AMBIGUOUS
    death = tracker.observe(parse("You are dead! Sorry...\r\n", WIRE))
    assert death.confidence is PositionConfidence.UNKNOWN
