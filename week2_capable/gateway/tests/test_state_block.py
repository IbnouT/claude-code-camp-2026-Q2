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
    lines = block.splitlines()
    assert lines[0] == "[here] The Temple Of Midgaard"
    assert lines[1] == "exits: north✓ | east?"
    assert lines[2] == "you: 20hp 100mana 82mv"
    assert lines[3] == "map: 2 rooms known · 2 with unexplored exits"


def test_block_stays_honest_when_nothing_is_known(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    block = render_state_block(store, _Pipeline(), _Projector(None))
    store.close()
    assert block.splitlines()[0] == "[here] position not yet observed"
    assert "map: 0 rooms known" in block
