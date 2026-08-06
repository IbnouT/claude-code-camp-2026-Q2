from __future__ import annotations

from pathlib import Path

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.profiles import PROFILES, Surface
from mud_gateway.state_notes import record_state_fields


class _Projector:
    def __init__(self, place: str | None) -> None:
        self.current_place_id = place


def test_fields_become_provisional_facts_with_model_provenance(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    recorded = record_state_fields(
        store,
        _Projector("place:s:1:1"),
        "session-1",
        7,
        perceive="dark",
        threat="a lurking cityguard",
        learned="the sewer grate opens south",
    )
    facts = {
        (fact.subject, fact.predicate): fact
        for fact in store.current_facts(layer="belief")
    }
    store.close()
    assert recorded["model.perceive"] == "dark"
    dark = facts[("place:s:1:1", "model.perceive")]
    assert dark.value == "dark"
    assert dark.confidence == "low"
    assert ("place:s:1:1", "model.threat") in facts
    assert ("place:s:1:1", "model.note") in facts


def test_unknown_perception_and_missing_place_write_nothing_spatial(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    recorded = record_state_fields(
        store, _Projector(None), "session-1", 9,
        perceive="unknown", learned="something durable",
    )
    facts = list(store.current_facts(layer="belief"))
    store.close()
    assert "model.perceive" not in recorded
    assert len(facts) == 1
    assert facts[0].subject == "session:session-1"
    assert facts[0].predicate == "model.note"


def test_knowledge_extensions_resolve_both_tools() -> None:
    surface = Surface(
        PROFILES["direct-full"],
        frozenset({"recall_state", "note_state"}),
    )
    names = {schema["name"] for schema in surface.schemas()}
    assert {"recall_state", "note_state"} <= names
    invocation = surface.resolve("note_state", {"perceive": "dark"})
    assert invocation.capability.name == "note_state"


def test_mission_readiness_reports_typed_snapshot(tmp_path: Path) -> None:
    import time as _time

    from mud_gateway.campaign import mission_readiness
    from mud_gateway.knowledge_models import EvidenceRef

    store = KnowledgeStore(tmp_path / "readiness.db", player_id="tester")
    evidence = EvidenceRef(
        session_id="test", source_seq=1, wire_digest="d",
        parser_version="p1", method="test", observed_at=_time.time(),
    )

    def fact(subject, predicate, value, layer):
        store.assert_fact(
            subject, predicate, value, layer=layer,
            confidence="confirmed", evidence=evidence, transaction_id="t1",
        )

    fact("player:tester", "state.hit", 40, "parsed")
    fact("player:tester", "state.max_hit", 46, "parsed")
    fact("player:tester", "state.level", 3, "parsed")
    fact("place:s:1:1", "title", "The Maze Entrance", "learned")
    fact("place:s:1:1", "exits", ["n"], "learned")
    fact("sighting:s:9:mob:0", "kind", "mob", "learned")
    fact("sighting:s:9:mob:0", "name", "The Massive Minotaur", "learned")
    fact("sighting:s:9:mob:0", "room", "place:s:1:1", "learned")

    report = mission_readiness(store, "minotaur")
    store.close()
    assert report["sighted_places"] == ["place:s:1:1"]
    assert report["sighted_titles"] == ["The Maze Entrance"]
    assert report["hit"] == 40 and report["max_hit"] == 46
    assert report["rooms_known"] == 1
    empty = report["frontier_remaining"]
    assert isinstance(empty, int)
