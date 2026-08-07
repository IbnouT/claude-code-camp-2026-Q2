from __future__ import annotations

import time
from pathlib import Path

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_models import EvidenceRef
from mud_gateway.state_block import render_state_block


class _Room:
    def __init__(self, title: str, exits: tuple[str, ...]) -> None:
        self.title = title
        self.exits = exits


class _Vitals:
    def __init__(self, hit: int, mana: int, move: int) -> None:
        self.hit = hit
        self.mana = mana
        self.move = move


class _Pipeline:
    def __init__(self, room=None, vitals=None) -> None:
        self.room = room
        self.vitals = vitals


class _Projector:
    def __init__(self, place: str | None) -> None:
        self.current_place_id = place


def _seed(store: KnowledgeStore) -> None:
    evidence = EvidenceRef(
        session_id="test", source_seq=1, wire_digest="d",
        parser_version="p1", method="test", observed_at=time.time(),
    )
    for subject, predicate, value in (
        ("place:s:1:1", "title", "The Temple Of Midgaard"),
        ("place:s:1:1", "exits", ["n", "e"]),
        ("place:s:1:1", "exit.north", "place:s:2:2"),
        ("place:s:2:2", "title", "Square"),
        ("place:s:2:2", "exits", ["s"]),
    ):
        store.assert_fact(
            subject, predicate, value,
            layer="learned", confidence="confirmed",
            evidence=evidence, transaction_id="t1",
        )


def test_block_shows_place_marked_exits_vitals_and_coverage(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _seed(store)
    block = render_state_block(
        store,
        _Pipeline(
            room=_Room("The Temple Of Midgaard", ("n", "e")),
            vitals=_Vitals(20, 100, 82),
        ),
        _Projector("place:s:1:1"),
    )
    store.close()
    assert "The Temple Of Midgaard" in block
    assert "north → Square" in block, "a known way says where it goes"
    assert "east → not walked yet" in block
    assert "20hp" in block and "82mv" in block
    assert "map: 2 rooms" in block


def test_block_stays_honest_when_nothing_is_known(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    block = render_state_block(store, _Pipeline(), _Projector(None))
    store.close()
    assert block.splitlines()[0] == "you have not seen where you are yet"
    assert "map: 0 rooms" in block


def test_the_block_says_where_a_known_way_goes(tmp_path: Path) -> None:
    """Knowing north is explored is useless. Knowing it reaches the Square
    is what lets the agent go back to somewhere it remembers."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _seed(store)
    block = render_state_block(
        store,
        _Pipeline(room=_Room("The Temple Of Midgaard", ("n", "e"))),
        _Projector("place:s:1:1"),
    )
    store.close()

    assert "north → Square" in block


def test_the_block_carries_what_a_fight_is_decided_on(tmp_path: Path) -> None:
    """Level, gold and hunger were absent, so no other thought was possible."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _seed(store)
    evidence = EvidenceRef(
        session_id="test", source_seq=2, wire_digest="d",
        parser_version="p1", method="score", observed_at=time.time(),
    )
    for predicate, value in (
        ("state.max_hit", 46), ("state.level", 3),
        ("state.gold", 120), ("state.hungry", True),
    ):
        store.assert_fact(
            "player:tester", predicate, value, layer="parsed",
            confidence="high", evidence=evidence,
        )
    block = render_state_block(
        store,
        _Pipeline(
            room=_Room("The Temple Of Midgaard", ("n",)),
            vitals=_Vitals(20, 100, 82),
        ),
        _Projector("place:s:1:1"),
        player_id="tester",
    )
    store.close()

    assert "20/46hp" in block
    assert "level 3" in block
    assert "gold 120" in block
    assert "hungry" in block


def test_advice_rides_with_the_situation(tmp_path: Path) -> None:
    """Rules the agent never reads are rules it does not have."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _seed(store)
    block = render_state_block(
        store,
        _Pipeline(room=_Room("The Temple Of Midgaard", ("n",))),
        _Projector("place:s:1:1"),
        advice="how to play:\n- size up anything before you fight it",
    )
    store.close()

    assert "size up anything before you fight it" in block
