from __future__ import annotations

from mud_gateway.observe import (
    Coverage,
    ExitsObservation,
    PlayerStateObservation,
    RoomObservation,
    UnparsedObservation,
    VitalsObservation,
    WireReference,
    normalized_text,
    parse,
)

WIRE = WireReference("recording.jsonl", 7, 7, "a" * 32)
ROOM = (
    "\x1b[0;33mThe Bakery\x1b[0m\r\n"
    "The smell of bread fills the air.\r\n"
    "\x1b[0;36m[ Exits: n e (s) ]\x1b[0m\r\n"
    "\x1b[0;32mA small sword lies here.\x1b[0m\r\n"
    "A cityguard stands here.\r\n"
    "20H 100M 82V > "
)


def test_room_exits_and_vitals_are_typed_from_one_frame():
    found = parse(ROOM, WIRE)
    room = next(item for item in found if isinstance(item, RoomObservation))
    exits = next(item for item in found if isinstance(item, ExitsObservation))
    vitals = next(item for item in found if isinstance(item, VitalsObservation))

    assert room.title == "The Bakery"
    assert room.exits == ("n", "e", "s")
    assert room.objects == ("A small sword lies here.",)
    assert room.mobs == ("A cityguard stands here.",)
    assert exits.exits == room.exits
    assert (vitals.hit, vitals.mana, vitals.move) == (20, 100, 82)


def test_every_observation_has_provenance_and_parser_metadata():
    for observation in parse(ROOM, WIRE):
        assert observation.wire_ref == WIRE
        assert observation.method
        assert observation.parser_version
        assert observation.confidence.value


def test_unknown_lines_are_retained_and_measured():
    found = parse("The moon glints oddly.\r\n", WIRE)
    assert isinstance(found[0], UnparsedObservation)
    coverage = Coverage()
    coverage.add(found)
    assert coverage.lines == 1
    assert coverage.typed == 0
    assert coverage.miss_rate == 1.0
    assert coverage.unparsed_samples == ["The moon glints oddly."]


def test_title_colour_needs_structural_support():
    found = parse(
        "\x1b[0;33mA janitor is walking around, cleaning up.\x1b[0m\r\n",
        WIRE,
    )
    assert not any(isinstance(item, RoomObservation) for item in found)


def test_second_title_colour_inside_room_is_content():
    found = parse(
        "\x1b[0;33mThe Grunting Boar\x1b[0m\r\n"
        "\x1b[0;36m[ Exits: n ]\x1b[0m\r\n"
        "\x1b[0;33mA singing, happy Drunk.\x1b[0m\r\n"
        "20H 100M 82V > ",
        WIRE,
    )
    rooms = [item for item in found if isinstance(item, RoomObservation)]
    assert len(rooms) == 1
    assert rooms[0].mobs == ("A singing, happy Drunk.",)


def test_wire_reference_digest_covers_exact_bytes():
    first = WireReference.from_bytes("session", 11, 12, b"hello")
    second = WireReference.from_bytes("session", 11, 12, b"hello!")
    assert first.digest != second.digest


def test_normalized_text_exposes_the_exact_plain_text_parser_input():
    assert normalized_text(
        b"\x1b[0;33mThe Bakery\x1b[0m\r\n"
        b"\r\n"
        b"  The smell of bread fills the air.  \r"
    ) == "The Bakery\nThe smell of bread fills the air."


def test_score_publishes_full_typed_player_state() -> None:
    found = parse(
        "You have 12(20) hit, 90(100) mana and 41(82) movement points.\r\n"
        "Your armor class is 9/10, and your alignment is -5.\r\n"
        "You have 14 exp, 23 gold coins, and 2 questpoints.\r\n"
        "This ranks you as a Newbie (level 2).\r\n"
        "You are standing.\r\n"
        "You are hungry.\r\n"
        "You are intoxicated.\r\n"
        "You are poisoned.\r\n"
        "12H 90M 41V > ",
        WIRE,
    )
    states = [
        item for item in found if isinstance(item, PlayerStateObservation)
    ]
    merged = {
        name: value
        for state in states
        for name, value in state.values.items()
    }

    assert merged == {
        "hit": 12,
        "max_hit": 20,
        "mana": 90,
        "max_mana": 100,
        "move": 41,
        "max_move": 82,
        "hungry": True,
        "thirsty": False,
        "drunk": True,
        "poisoned": True,
        "alignment": -5,
        "exp": 14,
        "gold": 23,
        "questpoints": 2,
        "level": 2,
        "posture": "standing",
    }
    assert all(state.kind == "player_state" for state in states)
    assert all(state.wire_ref == WIRE for state in states)


def test_player_state_deltas_capture_posture_and_conditions() -> None:
    found = parse(
        "You sit down and rest your tired bones.\r\n"
        "You are thirsty.\r\n"
        "20H 100M 82V > ",
        WIRE,
    )
    states = [
        item.values
        for item in found
        if isinstance(item, PlayerStateObservation)
    ]
    assert {"posture": "sitting"} in states
    assert {"thirsty": True} in states


def test_carry_failure_does_not_invent_an_encumbered_state() -> None:
    found = parse("You can't carry that much.\r\n20H 100M 82V > ", WIRE)

    states = [
        item.values
        for item in found
        if isinstance(item, PlayerStateObservation)
    ]

    assert all("encumbered" not in state for state in states)
