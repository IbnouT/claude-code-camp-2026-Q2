from __future__ import annotations

import asyncio
import time
from pathlib import Path

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_models import EvidenceRef
from mud_gateway.navigation import (
    NavigationExecutor,
    Room,
    WorldGraph,
    nearest_frontier,
    plan_route,
)
from mud_gateway.observe import VitalsObservation
from mud_gateway.profiles import PROFILES, Surface


def _graph() -> WorldGraph:
    return WorldGraph({
        "a": Room("a", "Temple", frozenset({"north", "east"}),
                  {"north": "b", "east": "c"}),
        "b": Room("b", "Square", frozenset({"south", "east"}),
                  {"south": "a"}),
        "c": Room("c", "Alley", frozenset({"west"}), {"west": "a"}),
        "d": Room("d", "Island", frozenset({"up"}), {}),
    })


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        session_id="test",
        source_seq=1,
        wire_digest="digest",
        parser_version="test-1",
        method="test",
        observed_at=time.time(),
    )


def test_graph_reads_places_exits_and_frontier(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    for subject, predicate, value in (
        ("place:s:1:1", "title", "Temple"),
        ("place:s:1:1", "exits", ["north", "east"]),
        ("place:s:1:1", "exit.north", "place:s:2:2"),
        ("place:s:2:2", "title", "Square"),
        ("place:s:2:2", "exits", ["south"]),
        ("player:tester", "state.hit", 20),
    ):
        store.assert_fact(
            subject, predicate, value,
            layer="learned", confidence="confirmed",
            evidence=evidence, transaction_id="t1",
        )
    graph = WorldGraph.from_store(store)
    store.close()
    assert set(graph.rooms) == {"place:s:1:1", "place:s:2:2"}
    temple = graph.rooms["place:s:1:1"]
    assert temple.links["north"] == "place:s:2:2"
    assert temple.frontier() == frozenset({"east"})
    assert graph.by_title("temple")[0] is temple


def test_route_finds_cheapest_path_and_respects_walls() -> None:
    graph = _graph()
    plan = plan_route(graph, "b", "c")
    assert plan is not None
    assert [step[0] for step in plan.steps] == ["south", "east"]
    assert plan_route(graph, "a", "d") is None
    walled = plan_route(
        graph, "b", "c",
        weight=lambda room, direction, target: (
            float("inf") if target == "a" else 1.0
        ),
    )
    assert walled is None


def test_nearest_frontier_prefers_close_rooms_and_skips_searched() -> None:
    graph = _graph()
    found = nearest_frontier(graph, "a")
    assert found is not None
    plan, direction = found
    assert plan.moves == 1
    assert plan.steps[-1][1] == "b"
    assert direction == "east"

    found = nearest_frontier(graph, "c", searched=("a", "c"))
    assert found is not None
    plan, direction = found
    assert plan.steps[-1][1] == "b"
    assert direction == "east"

    assert nearest_frontier(graph, "a", searched=("a", "b", "c")) is None


class _Projector:
    def __init__(self, place: str) -> None:
        self.current_place_id = place


class _Observations:
    def __init__(self, projector: _Projector, posture: str | None = None) -> None:
        self.knowledge = projector
        self.posture = posture


class _Position:
    certain = True


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, session, kind, payload, trace_id=None):
        self.events.append((kind, payload))

    def last_seq(self, session) -> int:
        return len(self.events)


class _Reply:
    def __init__(self, observations=()) -> None:
        self.observations = tuple(observations)
        self.position = _Position()


class _Session:
    """Scripted world: moves relocate the projector along a room map."""

    def __init__(self, world: dict[str, dict[str, str]], start: str,
                 vitals: list[VitalsObservation] | None = None,
                 posture: str | None = None) -> None:
        self.id = "fake"
        self.world = world
        self.projector = _Projector(start)
        self.observations = _Observations(self.projector, posture)
        self.journal = _Journal()
        self.vitals = list(vitals or [])
        self.commands: list[str] = []

    async def command(self, line: str, trace_id=None) -> _Reply:
        self.commands.append(line)
        if line == "stand":
            self.observations.posture = "standing"
            return _Reply()
        here = self.projector.current_place_id
        target = self.world.get(here, {}).get(line)
        if target is not None:
            self.projector.current_place_id = target
        observations = ()
        if self.vitals:
            observations = (self.vitals.pop(0),)
        return _Reply(observations)


def _vitals(hit: int, move: int) -> VitalsObservation:
    kwargs = {"hit": hit, "mana": 100, "move": move}
    try:
        return VitalsObservation(**kwargs)  # type: ignore[arg-type]
    except TypeError:
        observation = VitalsObservation.__new__(VitalsObservation)
        for name, value in kwargs.items():
            object.__setattr__(observation, name, value)
        return observation


def _executor(session, store, **settings) -> NavigationExecutor:
    return NavigationExecutor(session, store, settings)


def test_travel_walks_the_learned_route(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    for subject, predicate, value in (
        ("place:s:1:1", "title", "Temple"),
        ("place:s:1:1", "exits", ["north"]),
        ("place:s:1:1", "exit.north", "place:s:2:2"),
        ("place:s:2:2", "title", "Square"),
        ("place:s:2:2", "exits", ["south", "east"]),
        ("place:s:2:2", "exit.south", "place:s:1:1"),
        ("place:s:2:2", "exit.east", "place:s:3:3"),
        ("place:s:3:3", "title", "Bakery"),
        ("place:s:3:3", "exits", ["west"]),
    ):
        store.assert_fact(
            subject, predicate, value,
            layer="learned", confidence="confirmed",
            evidence=evidence, transaction_id="t1",
        )
    session = _Session(
        {
            "place:s:1:1": {"north": "place:s:2:2"},
            "place:s:2:2": {"east": "place:s:3:3"},
        },
        "place:s:1:1",
    )
    report = asyncio.run(
        _executor(session, store).travel("Bakery")
    )
    store.close()
    assert report.stop == "arrived"
    assert report.arrived is True
    assert session.commands == ["north", "east"]


def test_travel_can_be_disabled_by_its_setting(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    session = _Session({}, "place:s:1:1")
    report = asyncio.run(
        _executor(session, store, travel_enabled=False).travel("Bakery")
    )
    store.close()
    assert report.stop == "travel_disabled"
    assert session.commands == []


def test_sweep_stops_interrupted_when_health_drops(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    for subject, predicate, value in (
        ("place:s:1:1", "title", "Temple"),
        ("place:s:1:1", "exits", ["north"]),
        ("place:s:1:1", "exit.north", "place:s:9:9"),
        ("place:s:9:9", "title", "Dark Lane"),
        ("place:s:9:9", "exits", ["north", "south"]),
        ("place:s:9:9", "exit.south", "place:s:1:1"),
    ):
        store.assert_fact(
            subject, predicate, value,
            layer="learned", confidence="confirmed",
            evidence=evidence, transaction_id="t1",
        )
    session = _Session(
        {"place:s:1:1": {"north": "place:s:9:9"}},
        "place:s:1:1",
        vitals=[_vitals(20, 80), _vitals(12, 78)],
    )
    executor = _executor(session, store)
    first = asyncio.run(executor.sweep())
    store.close()
    assert first.stop == "interrupted"


def test_surface_extensions_add_tools_without_touching_the_profile() -> None:
    baseline = Surface(PROFILES["direct-full"])
    extended = Surface(
        PROFILES["direct-full"], frozenset({"sweep", "travel_to"})
    )
    names = {schema["name"] for schema in extended.schemas()}
    assert {"sweep", "travel_to"} <= names
    assert len(extended.schemas()) == len(baseline.schemas()) + 2
    assert baseline.measurement()["extensions"] == []
    invocation = extended.resolve("travel_to", {"destination": "Bakery"})
    assert invocation.capability.name == "travel_to"

def test_by_title_falls_back_to_containment() -> None:
    graph = WorldGraph({
        "a": Room("a", "The Temple Of Midgaard", frozenset(), {}),
        "b": Room("b", "Temple", frozenset(), {}),
    })
    assert [room.place_id for room in graph.by_title("Temple")] == ["b"]
    assert [
        room.place_id for room in graph.by_title("temple of midgaard")
    ] == ["a"]
    assert graph.by_title("bakery") == []


def test_sweep_looks_once_before_declaring_the_frontier_empty(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    session = _Session({}, "place:s:1:1")
    report = asyncio.run(_executor(session, store).sweep())
    store.close()
    assert report.stop == "frontier_exhausted"
    assert session.commands == ["look"]


def test_graph_canonicalizes_abbreviated_exits(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    for subject, predicate, value in (
        ("place:s:1:1", "title", "Temple"),
        ("place:s:1:1", "exits", ["n", "e"]),
        ("place:s:1:1", "exit.north", "place:s:2:2"),
    ):
        store.assert_fact(
            subject, predicate, value,
            layer="learned", confidence="confirmed",
            evidence=evidence, transaction_id="t1",
        )
    graph = WorldGraph.from_store(store)
    store.close()
    room = graph.rooms["place:s:1:1"]
    assert room.exits == frozenset({"north", "east"})
    assert room.frontier() == frozenset({"east"})


def _two_room_store(tmp_path: Path) -> KnowledgeStore:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    for subject, predicate, value in (
        ("place:s:1:1", "title", "Temple"),
        ("place:s:1:1", "exits", ["north"]),
        ("place:s:1:1", "exit.north", "place:s:2:2"),
        ("place:s:2:2", "title", "Square"),
        ("place:s:2:2", "exits", ["south"]),
    ):
        store.assert_fact(
            subject, predicate, value,
            layer="learned", confidence="confirmed",
            evidence=evidence, transaction_id="t1",
        )
    return store


def test_a_resting_character_stands_before_walking(tmp_path: Path) -> None:
    """A resting character refuses every move, so the routine stands first."""
    store = _two_room_store(tmp_path)
    session = _Session(
        {"place:s:1:1": {"north": "place:s:2:2"}},
        "place:s:1:1",
        posture="resting",
    )
    report = asyncio.run(_executor(session, store).travel("Square"))
    store.close()

    assert session.commands[0] == "stand"
    assert "north" in session.commands
    assert report.arrived is True


def test_a_standing_character_is_not_told_to_stand(tmp_path: Path) -> None:
    store = _two_room_store(tmp_path)
    session = _Session(
        {"place:s:1:1": {"north": "place:s:2:2"}},
        "place:s:1:1",
        posture="standing",
    )
    asyncio.run(_executor(session, store).travel("Square"))
    store.close()

    assert "stand" not in session.commands


def test_the_map_joins_rooms_when_identity_was_recorded(tmp_path: Path) -> None:
    """Two runs of the same ground become one map, not two copies."""
    from mud_gateway.identity import record

    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    for subject, predicate, value in (
        ("place:s1:1:1", "title", "The Armory"),
        ("place:s1:1:1", "exits", ["north"]),
        ("place:s1:1:1", "exit.north", "place:s1:2:1"),
        ("place:s1:2:1", "title", "Main Street"),
        ("place:s1:2:1", "exits", ["south"]),
        ("place:s2:1:1", "title", "The Armory"),
        ("place:s2:1:1", "exits", ["north"]),
        ("place:s2:9:1", "title", "The Bakery"),
        ("place:s2:9:1", "exits", ["west"]),
    ):
        store.assert_fact(
            subject, predicate, value, layer="learned",
            confidence="confirmed", evidence=evidence, transaction_id="t1",
        )

    before = WorldGraph.from_store(store)
    assert len([r for r in before.rooms.values() if r.title == "The Armory"]) == 2

    record(store, store.current_facts(layer="learned"))
    after = WorldGraph.from_store(store)
    store.close()

    armories = [r for r in after.rooms.values() if r.title == "The Armory"]
    assert len(armories) == 1
    assert "north" in armories[0].links


def test_the_map_reads_places_when_identity_was_never_recorded(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    store.assert_fact(
        "place:s1:1:1", "title", "The Armory", layer="learned",
        confidence="confirmed", evidence=evidence, transaction_id="t1",
    )
    graph = WorldGraph.from_store(store)
    store.close()
    assert list(graph.rooms) == ["place:s1:1:1"]
