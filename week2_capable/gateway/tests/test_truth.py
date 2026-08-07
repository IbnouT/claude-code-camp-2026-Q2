"""Observer truth: recorded for grading, never readable by the agent."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_models import EvidenceRef
from mud_gateway.truth import LAYER, PREDICATE, RoomNumbers


class _Admin:
    """An immortal connection scripted to answer where the player is."""

    def __init__(self, answers) -> None:
        self.answers = list(answers)
        self.asked = 0

    async def locate(self, character: str):
        self.asked += 1
        return self.answers.pop(0) if self.answers else None


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        session_id="s1", source_seq=1, wire_digest="d" * 64,
        parser_version="1", method="test", observed_at=time.time(),
    )


def _store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")


def test_a_settled_room_number_is_recorded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    admin = _Admin([(3005, "The Temple Square"), (3005, "The Temple Square")])
    numbers = RoomNumbers(admin, store, "poucet")

    result = asyncio.run(numbers.observe("place:s1:1:1", _evidence()))

    assert result == 3005
    facts = store.current_facts(layer=LAYER)
    assert [(f.subject, f.predicate, f.value) for f in facts] == [
        ("place:s1:1:1", PREDICATE, 3005)
    ]
    store.close()


def test_a_character_that_moved_mid_reading_records_nothing(
    tmp_path: Path,
) -> None:
    """Fleeing between the two readings leaves no single answer to record."""
    store = _store(tmp_path)
    admin = _Admin([(3005, "The Temple Square"), (3001, "The Temple")])
    numbers = RoomNumbers(admin, store, "poucet")

    result = asyncio.run(numbers.observe("place:s1:1:1", _evidence()))

    assert result is None
    assert store.current_facts(layer=LAYER) == []
    assert numbers.skipped == 1
    store.close()


def test_the_agent_facing_layers_never_carry_room_numbers(
    tmp_path: Path,
) -> None:
    """What the agent reads must not contain what only an observer knows."""
    store = _store(tmp_path)
    admin = _Admin([(3005, "The Temple Square"), (3005, "The Temple Square")])
    asyncio.run(RoomNumbers(admin, store, "poucet").observe(
        "place:s1:1:1", _evidence()
    ))

    for layer in ("belief", "parsed", "learned", "derived"):
        assert store.current_facts(layer=layer) == []
    store.close()


def test_nothing_is_recorded_without_a_place(tmp_path: Path) -> None:
    store = _store(tmp_path)
    admin = _Admin([(3005, "The Temple Square")])
    result = asyncio.run(RoomNumbers(admin, store, "poucet").observe(
        None, _evidence()
    ))
    assert result is None
    assert admin.asked == 0
    store.close()


def test_a_reading_naming_another_room_is_not_recorded(tmp_path: Path) -> None:
    """Both readings agree, but on a room the character has moved to."""
    store = _store(tmp_path)
    admin = _Admin([(3001, "The Temple"), (3001, "The Temple")])
    numbers = RoomNumbers(admin, store, "poucet")

    result = asyncio.run(numbers.observe(
        "place:s1:1:1", _evidence(), expected_title="The Temple Square"
    ))

    assert result is None
    assert store.current_facts(layer=LAYER) == []
    assert numbers.skipped == 1
    store.close()
