"""The observer answers the harness, and never the agent.

Two things have to hold. The room number reaches the record, so a room
is the same room on the second visit. And it reaches nothing the agent
is shown, whatever shape that payload takes.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from mud_gateway.session import LoginFailed
from mud_gateway.observer import INVISIBILITY, RoomObserver


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, session, kind, payload, trace_id=None):
        self.events.append((kind, payload))
        return type("Event", (), {"seq": len(self.events)})()

    def last_seq(self, session) -> int:
        return len(self.events)

    def of(self, kind: str) -> list[dict]:
        return [payload for name, payload in self.events if name == kind]


class _AdminSession:
    """Stands in for the immortal connection, recording what it was told."""

    def __init__(self, answers=None, fail_on=None) -> None:
        self.answers = list(answers or [(3041, "Inside The East Gate")])
        self.fail_on = fail_on or set()
        self.commands: list[str] = []
        self.opened = 0
        self.closed = 0

    async def open(self) -> None:
        self.opened += 1
        if "open" in self.fail_on:
            raise LoginFailed("refused")

    async def close(self) -> None:
        self.closed += 1

    async def set_field(self, player, field, value, *, offline=False):
        self.commands.append(f"set {player} {field} {value}")
        return "ok"

    async def locate(self, player):
        self.commands.append("where")
        if "locate" in self.fail_on:
            raise LoginFailed("connection lost")
        return self.answers.pop(0) if self.answers else None


def _observer(journal, session, **kwargs):
    observer = RoomObserver(
        journal,
        character="admin",
        password="secret",
        host="h",
        port=1,
        watching="poucet",
        session_id="s1",
        **kwargs,
    )
    observer._build = lambda: session  # type: ignore[attr-defined]
    return observer


def _opened(journal, session, monkeypatch):
    import mud_gateway.observer as module
    monkeypatch.setattr(module, "AdminSession", lambda *a, **k: session)
    observer = RoomObserver(
        journal, character="admin", password="secret", host="h", port=1,
        watching="poucet", session_id="s1",
    )
    assert asyncio.run(observer.open()) is True
    return observer


def test_the_observer_hides_itself_with_a_stated_level(monkeypatch) -> None:
    """A bare toggle would undo the invisibility a character already has."""
    journal, session = _Journal(), _AdminSession()
    _opened(journal, session, monkeypatch)

    assert session.commands == [f"set admin invis {INVISIBILITY}"]


def test_the_room_number_reaches_the_record(monkeypatch) -> None:
    journal, session = _Journal(), _AdminSession(
        [(3041, "East Gate"), (3041, "East Gate")])
    observer = _opened(journal, session, monkeypatch)

    assert asyncio.run(observer.room_number()) == 3041


def test_a_move_between_the_two_asks_keeps_both_rooms(monkeypatch) -> None:
    """Both are real. The reply was read in the first, we are in the
    second, and losing either would lose a room from the map."""
    journal, session = _Journal(), _AdminSession(
        [(3041, "East Gate"), (3001, "The Temple")])
    observer = _opened(journal, session, monkeypatch)

    assert asyncio.run(observer.room_number()) == 3041
    assert observer.moved_to == 3001
    moved = [n for n in journal.of("observer") if n["phase"] == "moved"]
    assert moved == [{"phase": "moved", "from": 3041, "to": 3001}]


def test_no_password_means_no_observer_and_no_failure() -> None:
    """A run without an immortal password plays exactly as it does today."""
    journal = _Journal()
    observer = RoomObserver(
        journal, character="admin", password=None, host="h", port=1,
        watching="poucet", session_id="s1",
    )

    assert asyncio.run(observer.open()) is False
    assert observer.available is False
    assert asyncio.run(observer.room_number()) is None
    assert journal.of("observer")[0]["reason"] == "no immortal password"


def test_a_refused_connection_leaves_the_run_alone(monkeypatch) -> None:
    journal = _Journal()
    session = _AdminSession(fail_on={"open"})
    import mud_gateway.observer as module
    monkeypatch.setattr(module, "AdminSession", lambda *a, **k: session)
    observer = RoomObserver(
        journal, character="admin", password="secret", host="h", port=1,
        watching="poucet", session_id="s1",
    )

    assert asyncio.run(observer.open()) is False
    assert asyncio.run(observer.room_number()) is None


def test_a_lost_observer_reconnects_and_asks_again(monkeypatch) -> None:
    """Reconnecting is only worth doing if the question gets answered."""
    journal = _Journal()
    session = _AdminSession([(3041, "East Gate"), (3041, "East Gate")],
                            fail_on={"locate"})

    async def _locate(player):
        session.commands.append("where")
        if "locate" in session.fail_on:
            session.fail_on.discard("locate")
            raise LoginFailed("connection lost")
        return session.answers.pop(0) if session.answers else None

    session.locate = _locate
    observer = _opened(journal, session, monkeypatch)

    assert asyncio.run(observer.room_number()) == 3041
    assert [n["phase"] for n in journal.of("observer")].count("lost") == 1
    assert session.opened == 2, "it came back"


def test_the_observer_only_ever_asks(monkeypatch) -> None:
    """Nothing it sends can change the world the agent is playing in."""
    journal, session = _Journal(), _AdminSession(
        [(3041, "East Gate"), (3041, "East Gate")])
    observer = _opened(journal, session, monkeypatch)
    asyncio.run(observer.room_number())
    asyncio.run(observer.close())

    moving = {"goto", "transfer", "trans", "teleport", "purge", "load",
              "restore", "set admin room", "force", "slay"}
    for command in session.commands:
        assert not any(command.startswith(word) for word in moving), command


# -- the invariant that matters ----------------------------------------


class _Session:
    def __init__(self) -> None:
        self.id = "s1"
        self.journal = _Journal()
        self.observer = None
        self.observations = type("O", (), {"knowledge": None})()


def test_the_number_is_journalled_but_not_returned(monkeypatch) -> None:
    """It belongs in the record, and in nothing the agent is handed."""
    from mud_gateway.session import Session

    journal = _Journal()
    session = Session.__new__(Session)
    session.id = "s1"
    session.journal = journal

    class _Observer:
        available = True

        async def room_number(self):
            return 3041

    session.observer = _Observer()
    session._reused = False
    position = type("P", (), {"title": "East Gate", "place": 7})()
    session._note_room_number(3041, position, "t1")

    recorded = journal.of("room_number")
    assert recorded == [{"number": 3041, "title": "East Gate"}]


def test_without_an_observer_nothing_is_recorded() -> None:
    from mud_gateway.session import Session

    journal = _Journal()
    session = Session.__new__(Session)
    session.id = "s1"
    session.journal = journal
    session.observer = None
    session._reused = False
    session._note_room_number(None, object(), "t1")

    assert journal.of("room_number") == []


def test_no_agent_facing_payload_carries_a_room_number() -> None:
    """The guarantee, over the shapes the agent actually receives.

    Every one of these is serialised whole into a tool result, so a room
    number appearing in any of them would reach the model. This is the
    check that has to keep holding when rooms are keyed by the number.
    """
    from mud_gateway.campaign import readiness_text
    from mud_gateway.navigation.executor import RoutineReport

    report = RoutineReport(
        routine="sweep", stop="time_limit", steps=4, rooms_seen=3,
        rooms_new=2, frontier_remaining=1, move_points=40,
    )
    readiness = readiness_text({
        "target": "minotaur",
        "sighted_places": [],
        "sighted_titles": ["The Temple"],
        "hit": 40,
    })

    for payload in (report.text(), readiness):
        assert "3041" not in payload
        assert "room_number" not in payload
        for key in json.loads(payload):
            assert "vnum" not in key.lower()


# -- the number actually reaching the store ----------------------------


def _store(tmp_path):
    from mud_gateway.knowledge import KnowledgeStore
    return KnowledgeStore(tmp_path / "k.db", player_id="tester")


def _frame(projector, title, number, move=None):
    """One arrival, as the pipeline delivers it."""
    from mud_gateway.observe import RoomObservation, WireReference
    from mud_gateway.position import PositionConfidence, PositionObservation
    ref = WireReference(source="s1", first_seq=1, last_seq=2, digest="d")
    room = RoomObservation.__new__(RoomObservation)
    for name, value in (
        ("kind", "room"), ("title", title), ("exits", ("north",)),
        ("description", ()), ("wire_ref", ref), ("text", title),
        ("confidence", PositionConfidence.CONFIRMED),
        ("parser_version", "t"), ("method", "t"), ("values", {}),
    ):
        object.__setattr__(room, name, value)
    position = PositionObservation(
        1, title, PositionConfidence.CONFIRMED, "test", ref)
    projector.ingest([room], position, attempted_move=move, room_number=number)


def test_a_numbered_room_is_stored_under_its_number(tmp_path) -> None:
    from mud_gateway.knowledge_projection import KnowledgeProjector
    store = _store(tmp_path)
    projector = KnowledgeProjector(store, player_id="tester")
    _frame(projector, "The Temple", 3001)
    subjects = {f.subject for f in store.current_facts(layer="learned")}
    store.close()

    assert "room:3001" in subjects


def test_walking_back_returns_to_the_same_subject(tmp_path) -> None:
    """The whole point: one number, one room, however often we return."""
    from mud_gateway.knowledge_projection import KnowledgeProjector
    store = _store(tmp_path)
    projector = KnowledgeProjector(store, player_id="tester")
    _frame(projector, "The Temple", 3001)
    _frame(projector, "Main Street", 3016, move="north")
    _frame(projector, "The Temple", 3001, move="south")
    rooms = {f.subject for f in store.current_facts(layer="learned")
             if f.predicate == "title"}
    store.close()

    assert rooms == {"room:3001", "room:3016"}


def test_visits_count_up_across_arrivals(tmp_path) -> None:
    """It stayed at one when written to a layer that never supersedes."""
    from mud_gateway.knowledge_projection import KnowledgeProjector
    from mud_gateway.state_block import _visits
    store = _store(tmp_path)
    projector = KnowledgeProjector(store, player_id="tester")
    for _ in range(3):
        _frame(projector, "The Temple", 3001)
        _frame(projector, "Main Street", 3016, move="north")
    seen = _visits(store, "room:3001")
    store.close()

    assert seen == 3, "three arrivals, counted three"


def test_an_unanswered_observer_does_not_split_the_room(tmp_path) -> None:
    """A dropped answer used to mint a twin nothing could merge back."""
    from mud_gateway.knowledge_projection import KnowledgeProjector
    store = _store(tmp_path)
    projector = KnowledgeProjector(store, player_id="tester")
    _frame(projector, "The Temple", 3001)
    _frame(projector, "The Temple", None)
    rooms = {f.subject for f in store.current_facts(layer="learned")
             if f.predicate == "title"}
    store.close()

    assert rooms == {"room:3001"}


def test_a_numbered_store_ignores_rooms_from_before(tmp_path) -> None:
    """Legacy subjects never joined, and would report an unreachable map."""
    from mud_gateway.knowledge_models import EvidenceRef
    from mud_gateway.navigation.graph import WorldGraph
    import time
    store = _store(tmp_path)
    evidence = EvidenceRef(session_id="s", source_seq=1, wire_digest="d",
                           parser_version="t", method="t",
                           observed_at=time.time())
    for subject, title in (("place:old:1:1", "The Temple"),
                           ("room:3001", "The Temple")):
        store.assert_fact(subject, "title", title, layer="learned",
                          confidence="confirmed", evidence=evidence,
                          transaction_id="t1")
    graph = WorldGraph.from_store(store)
    store.close()

    assert set(graph.rooms) == {"room:3001"}


# -- asking only when the room can have changed ------------------------


class _Counting:
    available = True

    def __init__(self, number=3041) -> None:
        self.number = number
        self.asks = 0

    async def room_number(self):
        self.asks += 1
        return self.number


def _bare_session(observer):
    from mud_gateway.session import Session
    session = Session.__new__(Session)
    session.id = "s1"
    session.journal = _Journal()
    session.observer = observer
    session._room = None
    session.observations = type("O", (), {"room": None})()
    return session


def test_a_command_that_cannot_move_us_reuses_the_number() -> None:
    """Two immortal round trips a command is the cost being avoided."""
    observer = _Counting()
    session = _bare_session(observer)
    asyncio.run(session._room_number("north", ()))
    for line in ("look", "exits", "score", "inventory", "get all"):
        asyncio.run(session._room_number(line, ()))

    assert observer.asks == 1, "asked once, for the move"


def test_every_way_of_being_moved_asks_again() -> None:
    observer = _Counting()
    session = _bare_session(observer)
    for line in ("north", "flee", "recall", "enter portal", "follow guard"):
        asyncio.run(session._room_number(line, ()))

    assert observer.asks == 5


def test_a_fight_does_not_ask_every_round() -> None:
    """Combat sends a line a round and moves nobody. Judging by arrival
    rather than by content would spend two immortal calls a round."""
    observer = _Counting()
    session = _bare_session(observer)
    session._room = 3041
    session.observations = type("O", (), {"room": _room("The East Gate")})()
    for _ in range(10):
        asyncio.run(session._room_number("", ()))

    assert observer.asks == 0


def test_output_arriving_unbidden_asks_when_it_names_a_new_room() -> None:
    """A death arrives unbidden and does move us."""
    observer = _Counting(3001)
    session = _bare_session(observer)
    session._room = 3041
    session.observations = type("O", (), {"room": _room("The East Gate")})()

    assert asyncio.run(session._room_number("", (_room("The Temple"),))) == 3001
    assert observer.asks == 1


def test_not_knowing_where_we_are_always_asks() -> None:
    observer = _Counting()
    session = _bare_session(observer)
    asyncio.run(session._room_number("score", ()))

    assert observer.asks == 1


def _room(title):
    """A parsed room observation, as the reply would produce."""
    from mud_gateway.observe import RoomObservation, WireReference
    from mud_gateway.position import PositionConfidence
    ref = WireReference(source="s", first_seq=1, last_seq=2, digest="d")
    room = RoomObservation.__new__(RoomObservation)
    for name, value in (
        ("kind", "room"), ("title", title), ("exits", ()),
        ("description", ()), ("wire_ref", ref), ("text", title),
        ("confidence", PositionConfidence.CONFIRMED),
        ("parser_version", "t"), ("method", "t"), ("values", {}),
    ):
        object.__setattr__(room, name, value)
    return room


def test_dying_in_a_fight_asks_although_nothing_moved_us() -> None:
    """The command was an attack, and the reply is the Temple."""
    observer = _Counting(3001)
    session = _bare_session(observer)
    session._room = 3050
    session.observations = type("O", (), {"room": _room("The Dark Cave")})()

    number = asyncio.run(
        session._room_number("attack minotaur", (_room("The Temple"),))
    )

    assert observer.asks == 1, "the room named is not the room we hold"
    assert number == 3001


def test_standing_still_in_the_room_we_hold_asks_nothing() -> None:
    observer = _Counting()
    session = _bare_session(observer)
    session._room = 3041
    session.observations = type("O", (), {"room": _room("The East Gate")})()

    number = asyncio.run(
        session._room_number("look", (_room("The East Gate"),))
    )

    assert observer.asks == 0
    assert number == 3041


def test_the_observer_writes_into_the_session_it_serves(monkeypatch) -> None:
    """One session, one flow. A failed immortal command has to be findable
    beside the player commands it happened between, not in a record of its
    own that nobody opens."""
    import mud_gateway.observer as module
    seen = {}

    class _Spy:
        def __init__(self, journal, **kwargs):
            seen.update(kwargs)

        async def open(self): ...
        async def close(self): ...
        async def set_field(self, *a, **k): return "ok"
        async def locate(self, player): return (3041, "East Gate")

    monkeypatch.setattr(module, "AdminSession", _Spy)
    observer = RoomObserver(
        _Journal(), character="admin", password="secret", host="h", port=1,
        watching="poucet", session_id="the-session",
    )
    asyncio.run(observer.open())

    assert seen["session_id"] == "the-session"


def test_the_observer_connection_is_marked_as_its_own(monkeypatch) -> None:
    import mud_gateway.observer as module
    seen = {}

    class _Spy:
        def __init__(self, journal, **kwargs):
            seen.update(kwargs)

        async def open(self): ...
        async def close(self): ...
        async def set_field(self, *a, **k): return "ok"
        async def locate(self, player): return (3041, "East Gate")

    monkeypatch.setattr(module, "AdminSession", _Spy)
    observer = RoomObserver(
        _Journal(), character="admin", password="secret", host="h", port=1,
        watching="poucet", session_id="the-session",
    )
    asyncio.run(observer.open())

    from mud_gateway.admin import AdminSession
    from mud_gateway.journal import Journal
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        journal = Journal(pathlib.Path(directory) / "j.db")
        admin = AdminSession(
            journal, name="admin", password="x", session_id="s",
        )
        assert admin.session.issuer == "gateway-admin"
        assert admin.session.observes is False
        journal.close()


def test_every_command_records_who_it_was_sent_for(tmp_path) -> None:
    """Counting what a session did has to be able to leave out the work
    nobody asked for."""
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from test_session import ScriptedTransport
    from mud_gateway.journal import Journal
    from mud_gateway.session import Session

    journal = Journal(tmp_path / "j.db")
    session = Session(journal, name="poucet", password="x")
    session.transport = ScriptedTransport([b"You look around.\r\n1H 2M 3V > "])
    session._logged_in = True
    asyncio.run(session.command("look"))
    asyncio.run(session.command("north", issuer="agent"))
    lines = [
        (event.payload["line"], event.payload["issuer"])
        for event in journal.since(session.id, kind="command")
    ]
    journal.close()

    assert ("look", "gateway") in lines
    assert ("north", "agent") in lines


def test_a_carried_number_is_not_recorded_as_a_reading() -> None:
    """A record saying the room was read on every command would say the
    immortal connection was asked when it never was."""
    observer = _Counting()
    session = _bare_session(observer)
    session.journal = _Journal()
    asyncio.run(session._room_number("north", ()))
    session._note_room_number(3041, object(), "t1")
    asyncio.run(session._room_number("score", ()))
    session._note_room_number(3041, object(), "t2")

    assert len(session.journal.of("room_number")) == 1


def test_a_mid_reading_move_leaves_us_holding_the_later_room() -> None:
    """The frame belongs to where it was read. We stand somewhere else."""
    class _Moving:
        available = True
        moved_to = 3001

        async def room_number(self):
            return 3041

    session = _bare_session(_Moving())
    session._room = 3050
    number = asyncio.run(session._room_number("north", ()))

    assert number == 3041, "the frame is recorded where it was read"
    assert session._room == 3001, "and we know we are no longer there"


def test_a_frame_with_no_number_is_skipped_not_twinned(tmp_path) -> None:
    """Once numbers are in use, a room without one has no honest subject.
    A twin would be dropped by the map and take its exit edge with it."""
    from mud_gateway.knowledge_projection import KnowledgeProjector
    store = _store(tmp_path)
    projector = KnowledgeProjector(store, player_id="tester")
    _frame(projector, "The Temple", 3001)
    _frame(projector, "Somewhere Else", None, move="north")
    subjects = {f.subject for f in store.current_facts(layer="learned")}
    store.close()

    assert subjects == {"room:3001"}
    assert projector.skipped == 1, "and the gap is counted, not silent"


def test_a_room_number_is_read_from_its_own_layer(tmp_path) -> None:
    """The same subject and predicate can hold a value per layer, so a
    lookup that ignores the layer answers with the wrong one."""
    from mud_gateway.knowledge_models import EvidenceRef
    import time
    store = _store(tmp_path)
    evidence = EvidenceRef(session_id="s", source_seq=1, wire_digest="d",
                           parser_version="t", method="t",
                           observed_at=time.time())
    for layer, value in (("parsed", 7), ("belief", 99)):
        store.assert_fact("room:3001", "visits", value, layer=layer,
                          confidence="tracked", evidence=evidence,
                          transaction_id=f"t-{layer}")
    found = store.current_fact("room:3001", "visits", layer="parsed")
    other = store.current_fact("room:3001", "visits", layer="belief")
    store.close()

    assert found is not None and found.value == 7
    assert other is not None and other.value == 99


def test_a_connection_that_does_not_observe_ingests_nothing() -> None:
    """Not the value of the flag, what the flag does. The immortal's own
    unbidden output must never become the player's position."""
    from mud_gateway.session import Session

    session = Session.__new__(Session)
    session.id = "s1"
    session.journal = _Journal()
    session.observes = False
    session.observer = None
    session._room = None
    session._reused = False
    ingested = []
    session.observations = type(
        "O", (), {"room": None, "ingest": lambda *a, **k: ingested.append(a)}
    )()

    assert session.observes is False
    assert ingested == []
