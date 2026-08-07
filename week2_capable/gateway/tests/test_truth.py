"""Observer truth: recorded for grading, never readable by the agent."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import json

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.truth import RoomNumbers


class _Admin:
    """An immortal connection scripted to answer where the player is."""

    def __init__(self, answers) -> None:
        self.answers = list(answers)
        self.asked = 0

    async def locate(self, character: str):
        self.asked += 1
        return self.answers.pop(0) if self.answers else None


def _recorded(tmp_path: Path) -> list[dict]:
    path = tmp_path / "observer" / "room-numbers.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _numbers(tmp_path: Path, admin) -> RoomNumbers:
    return RoomNumbers(
        admin, tmp_path / "observer" / "room-numbers.jsonl", "poucet"
    )


def test_a_settled_room_number_is_recorded(tmp_path: Path) -> None:
    admin = _Admin([(3005, "The Temple Square"), (3005, "The Temple Square")])
    result = asyncio.run(_numbers(tmp_path, admin).observe("place:s1:1:1"))

    assert result == 3005
    assert _recorded(tmp_path) == [{
        "session": "", "place": "place:s1:1:1",
        "room_number": 3005, "room_title": "The Temple Square",
    }]


def test_a_character_that_moved_mid_reading_records_nothing(
    tmp_path: Path,
) -> None:
    """Fleeing between the two readings leaves no single answer to record."""
    admin = _Admin([(3005, "The Temple Square"), (3001, "The Temple")])
    numbers = _numbers(tmp_path, admin)

    result = asyncio.run(numbers.observe("place:s1:1:1"))

    assert result is None
    assert _recorded(tmp_path) == []
    assert numbers.skipped == 1


def test_the_answer_key_never_enters_the_store_the_agent_reads(
    tmp_path: Path,
) -> None:
    """What only an observer knows must not be where the agent looks.

    Keeping it in a separate file makes that structural: there is nothing
    to filter out, because it was never put there.
    """
    admin = _Admin([(3005, "The Temple Square"), (3005, "The Temple Square")])
    asyncio.run(_numbers(tmp_path, admin).observe("place:s1:1:1"))

    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    for layer in ("belief", "parsed", "learned", "derived", "observer_truth"):
        assert store.current_facts(layer=layer) == []
    store.close()
    assert _recorded(tmp_path)[0]["room_number"] == 3005


def test_nothing_is_recorded_without_a_place(tmp_path: Path) -> None:
    admin = _Admin([(3005, "The Temple Square")])
    result = asyncio.run(_numbers(tmp_path, admin).observe(None))
    assert result is None
    assert admin.asked == 0


def test_a_reading_naming_another_room_is_not_recorded(tmp_path: Path) -> None:
    """Both readings agree, but on a room the character has moved to."""
    admin = _Admin([(3001, "The Temple"), (3001, "The Temple")])
    numbers = _numbers(tmp_path, admin)

    result = asyncio.run(numbers.observe(
        "place:s1:1:1", expected_title="The Temple Square"
    ))

    assert result is None
    assert _recorded(tmp_path) == []
    assert numbers.skipped == 1
