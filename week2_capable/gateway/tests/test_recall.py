"""Reading back what was seen, in words the agent can act on."""

from __future__ import annotations

import time
from pathlib import Path

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_models import EvidenceRef
from mud_gateway.navigation.graph import WorldGraph
from mud_gateway.recall import answer


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        session_id="s1", source_seq=1, wire_digest="d" * 64,
        parser_version="1", method="test", observed_at=time.time(),
    )


def _world(tmp_path: Path) -> KnowledgeStore:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    for subject, predicate, value, layer in (
        ("place:s1:1:1", "title", "The Temple Square", "learned"),
        ("place:s1:1:1", "exits", ["north", "east"], "learned"),
        ("place:s1:1:1", "exit.north", "place:s1:2:1", "learned"),
        ("place:s1:1:1", "passage.east", "refused", "parsed"),
        ("place:s1:2:1", "title", "The Temple", "learned"),
        ("place:s1:2:1", "exits", ["south", "up"], "learned"),
        ("room-sighting:1", "name", "a large minotaur", "learned"),
        ("room-sighting:1", "room", "place:s1:2:1", "learned"),
        ("place:s1:2:1", "service.bank", True, "belief"),
        ("player:tester", "state.hit", 30, "parsed"),
        ("player:tester", "state.max_hit", 46, "parsed"),
        ("player:tester", "state.level", 3, "parsed"),
        ("player:tester", "state.gold", 120, "parsed"),
        ("player:tester", "state.hungry", True, "parsed"),
    ):
        store.assert_fact(
            subject, predicate, value, layer=layer,
            confidence="confirmed" if layer == "learned" else "low",
            evidence=evidence,
        )
    return store


def test_here_names_the_room_its_exits_and_what_was_seen(tmp_path) -> None:
    store = _world(tmp_path)
    graph = WorldGraph.from_store(store)
    reply = answer(store, graph, "here", place_id="place:s1:1:1")
    store.close()

    assert "The Temple Square" in reply
    assert "north: The Temple" in reply
    assert "not walked yet" in reply
    assert "would not open" in reply


def test_a_target_that_was_seen_is_reported_with_its_room(tmp_path) -> None:
    store = _world(tmp_path)
    graph = WorldGraph.from_store(store)
    reply = answer(store, graph, "target", name="minotaur")
    store.close()

    assert "a large minotaur at The Temple" == reply


def test_a_target_never_seen_says_so_rather_than_guessing(tmp_path) -> None:
    store = _world(tmp_path)
    graph = WorldGraph.from_store(store)
    reply = answer(store, graph, "target", name="dragon")
    store.close()

    assert "not seen" in reply
    assert "dragon" in reply


def test_self_reports_what_decides_a_fight(tmp_path) -> None:
    store = _world(tmp_path)
    graph = WorldGraph.from_store(store)
    reply = answer(store, graph, "self", player_id="tester")
    store.close()

    assert "health 30 of 46" in reply
    assert "level 3" in reply
    assert "gold 120" in reply
    assert "hungry" in reply


def test_unexplored_names_where_there_is_still_ground(tmp_path) -> None:
    store = _world(tmp_path)
    graph = WorldGraph.from_store(store)
    reply = answer(store, graph, "unexplored", place_id="place:s1:1:1")
    store.close()

    assert "not walked yet" in reply


def test_services_report_where_they_were_recorded(tmp_path) -> None:
    store = _world(tmp_path)
    graph = WorldGraph.from_store(store)
    reply = answer(store, graph, "services")
    store.close()

    assert "bank at The Temple" in reply


def test_an_unknown_question_names_the_ones_that_exist(tmp_path) -> None:
    store = _world(tmp_path)
    graph = WorldGraph.from_store(store)
    reply = answer(store, graph, "weather")
    store.close()

    assert "creatures" in reply and "services" in reply


def test_an_empty_store_answers_honestly(tmp_path) -> None:
    store = KnowledgeStore(tmp_path / "empty.db", player_id="tester")
    graph = WorldGraph.from_store(store)
    replies = [
        answer(store, graph, "here", place_id="place:x:1:1"),
        answer(store, graph, "creatures"),
        answer(store, graph, "self", player_id="tester"),
    ]
    store.close()

    assert "not in what you have mapped" in replies[0]
    assert "have not seen any creature" in replies[1]
    assert "have not looked at yourself" in replies[2]


def test_the_tool_is_offered_only_with_the_knowledge_capability() -> None:
    """A tool the agent cannot call is the defect this feature exists to fix."""
    from mud_gateway.profiles import PROFILES, Surface

    plain = {schema["name"] for schema in Surface(PROFILES["direct-full"]).schemas()}
    assert "recall" not in plain

    with_knowledge = {
        schema["name"]
        for schema in Surface(
            PROFILES["direct-full"],
            extensions=frozenset({"recall"}),
        ).schemas()
    }
    assert "recall" in with_knowledge


def test_the_tool_states_the_questions_it_answers() -> None:
    """The model must be able to see what it may ask without guessing."""
    from mud_gateway.profiles import PROFILES, Surface
    from mud_gateway.recall import QUESTIONS

    schema = next(
        schema
        for schema in Surface(
            PROFILES["direct-full"], extensions=frozenset({"recall"})
        ).schemas()
        if schema["name"] == "recall"
    )
    choices = schema["inputSchema"]["properties"]["about"]["enum"]
    assert set(choices) == set(QUESTIONS)
