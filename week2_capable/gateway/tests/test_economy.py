from __future__ import annotations

import asyncio
import time
from pathlib import Path

from mud_gateway.economy import Economy
from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_models import EvidenceRef
from mud_gateway.state_notes import record_service


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, session, kind, payload, trace_id=None):
        self.events.append((kind, payload))


class _Session:
    def __init__(self) -> None:
        self.id = "fake"
        self.journal = _Journal()
        self.commands: list[str] = []

    async def command(self, line: str, trace_id=None):
        self.commands.append(line)
        return None


class _Projector:
    def __init__(self, place: str | None) -> None:
        self.current_place_id = place


class _TravelReport:
    def __init__(self, stop: str) -> None:
        self.stop = stop


class _Navigation:
    def __init__(self, graph, stop: str = "arrived") -> None:
        self.graph = graph
        self.stop = stop
        self.travelled: list[str] = []

    def _graph(self):
        return self.graph

    async def travel(self, destination: str):
        self.travelled.append(destination)
        return _TravelReport(self.stop)


class _GraphRoom:
    def __init__(self, title: str) -> None:
        self.title = title


class _Graph:
    def __init__(self, rooms: dict[str, str]) -> None:
        self.rooms = {
            place: _GraphRoom(title) for place, title in rooms.items()
        }

    def room_of(self, place_id):
        return place_id


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        session_id="test", source_seq=1, wire_digest="d",
        parser_version="p1", method="test", observed_at=time.time(),
    )


def _store(tmp_path: Path, gold: int | None = None) -> KnowledgeStore:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    if gold is not None:
        store.assert_fact(
            "player:tester", "state.gold", gold,
            layer="parsed", confidence="confirmed",
            evidence=_evidence(), transaction_id="t1",
        )
    return store


def test_recorded_service_becomes_a_belief_fact(tmp_path: Path) -> None:
    store = _store(tmp_path)
    recorded = record_service(
        store, _Projector("place:s:1:1"), "session-1", 3,
        kind="bank", detail="An automatic teller machine",
    )
    services = Economy(_Session(), store).known_services("bank")
    store.close()
    assert recorded["stored"] is True
    assert services == ["place:s:1:1"]


def test_surplus_is_deposited_at_the_recorded_bank(tmp_path: Path) -> None:
    store = _store(tmp_path, gold=75)
    record_service(
        store, _Projector("place:s:1:1"), "session-1", 3, kind="bank",
    )
    session = _Session()
    navigation = _Navigation(_Graph({"place:s:1:1": "The Temple Square"}))
    economy = Economy(session, store, navigation, {"carry_ceiling": 20})
    report = asyncio.run(economy.bank_surplus())
    store.close()
    assert report["stop"] == "deposited"
    assert report["deposited"] == 55
    assert navigation.travelled == ["The Temple Square"]
    assert session.commands == ["deposit 55"]


def test_custody_declines_with_typed_reasons(tmp_path: Path) -> None:
    store = _store(tmp_path, gold=10)
    economy = Economy(_Session(), store, None, {"carry_ceiling": 20})
    assert asyncio.run(economy.bank_surplus())["stop"] == "no_surplus"

    rich = _store(Path(tmp_path / "rich"), gold=100)
    (tmp_path / "rich").mkdir(exist_ok=True)
    store.close()
    economy = Economy(_Session(), rich, None, {"carry_ceiling": 20})
    assert asyncio.run(economy.bank_surplus())["stop"] == "no_known_bank"
    record_service(rich, _Projector("place:s:9:9"), "s", 1, kind="bank")
    economy = Economy(_Session(), rich, None, {"carry_ceiling": 20})
    assert asyncio.run(
        economy.bank_surplus()
    )["stop"] == "navigation_disabled"
    rich.close()
