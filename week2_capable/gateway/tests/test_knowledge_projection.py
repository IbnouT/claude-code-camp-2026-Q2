from __future__ import annotations

import sqlite3
from pathlib import Path

from mud_gateway.journal import Journal
from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_projection import KnowledgeProjector
from mud_gateway.observation_pipeline import ObservationPipeline
from mud_gateway.observe import WireReference

SCORE = (
    "You have 20(20) hit, 100(100) mana and 82(82) movement points.\r\n"
    "Your armor class is 9/10, and your alignment is 0.\r\n"
    "You have 0 exp, 7 gold coins, and 0 questpoints.\r\n"
    "This ranks you as a Newbie (level 1).\r\n"
    "You are standing.\r\n"
    "20H 100M 82V > "
)
ROOM = (
    "\x1b[0;33mThe Bakery\x1b[0m\r\n"
    "Warm bread fills the shelves.\r\n"
    "\x1b[0;36m[ Exits: south ]\x1b[0m\r\n"
    "\x1b[0;33mThe baker stands here.\x1b[0m\r\n"
    "20H 100M 82V > "
)


def test_pipeline_projects_player_state_and_room_with_provenance(
    tmp_path: Path,
) -> None:
    journal = Journal(tmp_path / "gateway.db")
    knowledge = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    pipeline = ObservationPipeline(
        journal,
        "gateway-alpha",
        knowledge=KnowledgeProjector(knowledge, player_id="alpha"),
    )

    pipeline.ingest(
        SCORE.encode("latin-1"),
        WireReference.from_bytes("gateway-alpha", 1, 3, SCORE),
    )
    pipeline.ingest(
        ROOM.encode("latin-1"),
        WireReference.from_bytes("gateway-alpha", 4, 6, ROOM),
        attempted_move="north",
    )

    facts = {
        (fact.subject, fact.predicate): fact
        for fact in knowledge.current_facts()
    }
    assert facts[("player:alpha", "state.gold")].value == 7
    assert facts[("player:alpha", "state.posture")].value == "standing"
    assert facts[("player:alpha", "state.poisoned")].value is False
    room_subject = next(
        subject
        for subject, predicate in facts
        if predicate == "title"
    )
    assert room_subject.startswith("place:gateway-alpha:")
    assert facts[(room_subject, "title")].value == "The Bakery"
    assert facts[(room_subject, "exits")].value == ["south"]
    assert facts[("player:alpha", "position")].value["place"] == room_subject
    assert all(
        fact.evidence.session_id == "gateway-alpha"
        for fact in facts.values()
    )
    pipeline.ingest(
        SCORE.encode("latin-1"),
        WireReference.from_bytes("gateway-alpha", 7, 9, SCORE),
    )
    updated_score = SCORE.replace("7 gold coins", "11 gold coins")
    pipeline.ingest(
        updated_score.encode("latin-1"),
        WireReference.from_bytes("gateway-alpha", 10, 12, updated_score),
    )
    assert {
        (fact.subject, fact.predicate): fact.value
        for fact in knowledge.current_facts(layer="parsed")
    }[("player:alpha", "state.gold")] == 11
    with sqlite3.connect(knowledge.path) as connection:
        position_evidence = connection.execute(
            "SELECT COUNT(*) FROM evidence_refs AS e "
            "JOIN assertions AS a ON a.assertion_id = e.assertion_id "
            "JOIN facts AS f ON f.fact_id = a.fact_id "
            "WHERE f.subject = 'player:alpha' AND f.predicate = 'position'"
        ).fetchone()[0]
        assert position_evidence == 1
    event = journal.since("gateway-alpha", kind="knowledge_change")[-1]
    assert event.payload["player_id"] == "alpha"
    assert event.payload["last_change_seq"] == knowledge.last_change_seq()


def test_room_sightings_do_not_collapse_duplicate_titles(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "gateway.db")
    knowledge = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    first = ObservationPipeline(
        journal,
        "gateway-alpha",
        knowledge=KnowledgeProjector(knowledge, player_id="alpha"),
    )
    second = ObservationPipeline(
        journal,
        "gateway-alpha",
        knowledge=KnowledgeProjector(knowledge, player_id="alpha"),
    )
    room = (
        "\x1b[0;33mA Hallway\x1b[0m\r\n"
        "\x1b[0;36m[ Exits: north south ]\x1b[0m\r\n"
        "20H 100M 82V > "
    )

    first.ingest(
        room.encode("latin-1"),
        WireReference.from_bytes("gateway-alpha", 1, 2, room),
    )
    second.ingest(
        room.encode("latin-1"),
        WireReference.from_bytes("gateway-alpha", 10, 12, room),
    )

    title_facts = [
        fact
        for fact in knowledge.current_facts(layer="learned")
        if fact.predicate == "title"
    ]
    assert len(title_facts) == 2
    assert title_facts[0].subject != title_facts[1].subject


def test_only_observed_traversal_creates_a_learned_exit(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "gateway.db")
    knowledge = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    pipeline = ObservationPipeline(
        journal,
        "gateway-alpha",
        knowledge=KnowledgeProjector(knowledge, player_id="alpha"),
    )
    first_room = (
        "\x1b[0;33mSouth Hall\x1b[0m\r\n"
        "\x1b[0;36m[ Exits: north ]\x1b[0m\r\n"
        "20H 100M 82V > "
    )
    second_room = (
        "\x1b[0;33mNorth Hall\x1b[0m\r\n"
        "\x1b[0;36m[ Exits: south ]\x1b[0m\r\n"
        "20H 100M 82V > "
    )

    pipeline.ingest(
        first_room.encode("latin-1"),
        WireReference.from_bytes("gateway-alpha", 1, 2, first_room),
    )
    pipeline.ingest(
        second_room.encode("latin-1"),
        WireReference.from_bytes("gateway-alpha", 3, 4, second_room),
        attempted_move="north",
    )

    facts = knowledge.current_facts(layer="learned")
    titles = {
        fact.value: fact.subject
        for fact in facts
        if fact.predicate == "title"
    }
    exit_fact = next(fact for fact in facts if fact.predicate == "exit.north")
    assert exit_fact.subject == titles["South Hall"]
    assert exit_fact.value == titles["North Hall"]
