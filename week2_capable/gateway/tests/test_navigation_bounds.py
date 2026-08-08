"""A routine has to finish inside the call that carries it.

The call is abandoned after a fixed number of seconds, so a routine that
only counts steps walks until it is cut off and reports nothing. These
cover the bound itself, what happens when it is passed anyway, and the
dispatch that turns a new stop reason into a stop rather than a hang.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_models import EvidenceRef
from mud_gateway.mcp_server import _navigation_refusal, execute, failure
from mud_gateway.navigation import NavigationExecutor
from mud_gateway.observe import VitalsObservation
from mud_gateway.profiles import CapabilityUnavailable, Surface, load_profile
from mud_gateway.settings import (
    GATEWAY_COMMAND,
    GatewaySettings,
    GatewaySettingsError,
    _call_ceiling,
)


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        session_id="test",
        source_seq=1,
        wire_digest="digest",
        parser_version="test-1",
        method="test",
        observed_at=time.time(),
    )


class _Clock:
    """A hand-wound clock, so no test waits for real seconds to pass."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Projector:
    def __init__(self, place: str) -> None:
        self.current_place_id = place


class _Observations:
    def __init__(self, projector, posture=None, vitals=None) -> None:
        self.knowledge = projector
        self.posture = posture
        self.vitals = vitals
        self.room = None


class _Position:
    certain = True


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, session, kind, payload, trace_id=None):
        self.events.append((kind, payload))

    def last_seq(self, session) -> int:
        return len(self.events)

    def kinds(self, kind: str) -> list[dict]:
        return [payload for name, payload in self.events if name == kind]


class _Reply:
    def __init__(self, observations=()) -> None:
        self.observations = tuple(observations)
        self.position = _Position()
        self.wire_ref = None


class _Session:
    """A scripted world whose every command can cost time on the clock."""

    def __init__(self, world, start, clock=None, seconds_per_command=0.0,
                 posture="standing", vitals=None) -> None:
        self.id = "fake"
        self.world = world
        self.clock = clock
        self.seconds_per_command = seconds_per_command
        self.projector = _Projector(start)
        self.observations = _Observations(self.projector, posture)
        self.journal = _Journal()
        self.commands: list[str] = []
        self.vitals = list(vitals or [])

    async def command(self, line: str, trace_id=None) -> _Reply:
        self.commands.append(line)
        if self.clock is not None:
            self.clock.advance(self.seconds_per_command)
        if line in ("exits", "look"):
            return _Reply()
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


def _corridor(store: KnowledgeStore, rooms: int) -> None:
    """A line of rooms, each with an unwalked way onward."""
    evidence = _evidence()
    for index in range(1, rooms + 1):
        place = f"place:s:{index}:{index}"
        facts = [("title", f"Room {index}"), ("exits", ["north"])]
        if index < rooms:
            facts.append(("exit.north", f"place:s:{index + 1}:{index + 1}"))
        for predicate, value in facts:
            store.assert_fact(
                place, predicate, value, layer="learned",
                confidence="confirmed", evidence=evidence,
                transaction_id=f"t{index}",
            )


def _world(rooms: int) -> dict[str, dict[str, str]]:
    return {
        f"place:s:{index}:{index}": {"north": f"place:s:{index + 1}:{index + 1}"}
        for index in range(1, rooms)
    }


# -- the bound itself ---------------------------------------------------


def test_a_sweep_stops_on_its_deadline_and_reports_the_ground_covered(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 20)
    clock = _Clock()
    # Three commands a step at a second each, against a four second margin,
    # so a step that starts before the deadline always ends before the call
    # does. That is the relationship the margin exists to hold.
    session = _Session(_world(20), "place:s:1:1", clock, 1.0)
    executor = NavigationExecutor(
        session, store, {"deadline_margin": 4.0},
        call_ceiling=30.0, clock=clock,
    )
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop == "time_limit"
    assert report.steps > 0, "it walked before it ran out of time"
    assert clock.now - 1000.0 < 30.0, "it stopped inside the call"


def test_a_step_offered_exactly_at_the_deadline_is_not_taken(
    tmp_path: Path,
) -> None:
    """The boundary belongs to stopping, not to one more step.

    A ceiling equal to the margin puts the deadline exactly at the moment
    the routine starts, which is the boundary itself and nothing near it.
    """
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 4)
    clock = _Clock()
    session = _Session(_world(4), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {"deadline_margin": 4.0},
        call_ceiling=4.0, clock=clock,
    )
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop == "time_limit"
    assert report.steps == 0
    assert not [line for line in session.commands
                if line in ("north", "south", "east", "west")]


def test_the_deadline_is_the_ceiling_less_the_margin(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 3)
    clock = _Clock()
    session = _Session(_world(3), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {"deadline_margin": 7.0},
        call_ceiling=30.0, clock=clock,
    )
    state = executor._start("sweep", {})
    store.close()

    assert state["deadline"] == pytest.approx(1000.0 + 23.0)


def test_a_route_walk_checks_the_deadline_between_its_own_steps(
    tmp_path: Path,
) -> None:
    """Travel walks a plan, so the plan cannot outrun the call either."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 6)
    clock = _Clock()
    session = _Session(_world(6), "place:s:1:1", clock, 3.0)
    executor = NavigationExecutor(
        session, store, {"deadline_margin": 4.0},
        call_ceiling=20.0, clock=clock,
    )
    report = asyncio.run(executor.travel("Room 6"))
    store.close()

    assert report.stop == "time_limit"
    assert not report.arrived
    assert clock.now - 1000.0 < 20.0


def test_travel_is_bounded_by_the_same_deadline_as_a_sweep(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 4)
    clock = _Clock()
    session = _Session(_world(4), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {"deadline_margin": 4.0},
        call_ceiling=4.0, clock=clock,
    )
    report = asyncio.run(executor.travel("Room 4"))
    store.close()

    assert report.stop == "time_limit"
    assert report.destination == "Room 4"


def test_without_a_ceiling_a_routine_is_bounded_only_by_its_steps(
    tmp_path: Path,
) -> None:
    """No ceiling means no deadline, never a deadline of zero."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 3)
    clock = _Clock()
    session = _Session(_world(3), "place:s:1:1", clock, 100.0)
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=None, clock=clock,
    )
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop != "time_limit"


# -- the step that cannot rest -----------------------------------------


def test_low_movement_stops_the_routine_and_does_not_rest(
    tmp_path: Path,
) -> None:
    """A rest cannot fit in a call, so the decision goes back to the model."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 4)
    clock = _Clock()
    session = _Session(
        _world(4), "place:s:1:1", clock, 0.0, vitals=[_vitals(40, 2)],
    )

    executor = NavigationExecutor(
        session, store, {"min_move_points": 15},
        call_ceiling=30.0, clock=clock,
    )
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop == "needs_rest"
    assert "rest" not in session.commands


def test_a_routine_never_leaves_the_character_seated(tmp_path: Path) -> None:
    """It stands to walk and never sits, so a cut cannot strand it seated."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 4)
    clock = _Clock()
    session = _Session(
        _world(4), "place:s:1:1", clock, 0.0, posture="resting",
        vitals=[_vitals(40, 2)],
    )
    executor = NavigationExecutor(
        session, store, {"min_move_points": 15},
        call_ceiling=30.0, clock=clock,
    )
    asyncio.run(executor.sweep())
    store.close()

    assert "rest" not in session.commands
    assert "stand" in session.commands
    assert session.observations.posture == "standing"


# -- outcomes the sweep has never seen ----------------------------------


def _refusing_after(executor: NavigationExecutor, walks: int, refusals: int = 8):
    """A step that walks normally, then refuses the way any step can.

    It refuses with a real stop reason rather than an error, which is what
    a deadline does, so the caller is being tested on how it reads an
    outcome and not on how it handles an exception.

    A caller that reads the refusal and carries on would spin forever, and
    it would spin without awaiting, so no timeout can end it: the event
    loop never runs to fire one. Refusing only so many times turns that
    hang into a failure with a sentence attached.
    """
    real_step = executor._step
    taken = {"count": 0, "refused": 0}

    async def _step(direction, expected, state, trace_id):
        if taken["count"] >= walks:
            taken["refused"] += 1
            if taken["refused"] > refusals:
                raise AssertionError(
                    f"the routine read {taken['refused']} refusals and kept "
                    "going. An outcome it does not know must stop it"
                )
            return "time_limit"
        taken["count"] += 1
        return await real_step(direction, expected, state, trace_id)

    return _step


def test_an_outcome_the_sweep_does_not_know_stops_it(tmp_path: Path) -> None:
    """Stopping is the default, so a new reason needs nothing remembered.

    A reason that fell through instead would spin: a step refused without
    awaiting leaves a loop with no await in it, which never yields, so the
    call could not even be cancelled.
    """
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 4)
    clock = _Clock()
    session = _Session(_world(4), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=30.0, clock=clock,
    )

    seen = {"count": 0}

    async def _invented(direction, expected, state, trace_id):
        seen["count"] += 1
        if seen["count"] > 8:
            raise AssertionError(
                "an unknown outcome was read eight times and never stopped "
                "the sweep"
            )
        return "a_reason_written_after_this_test"

    executor._step = _invented  # type: ignore[method-assign]
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop == "a_reason_written_after_this_test"


def test_a_refusal_during_the_route_walk_stops_the_sweep(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 6)
    clock = _Clock()
    session = _Session(_world(6), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=30.0, clock=clock,
    )
    executor._step = _refusing_after(executor, 2)  # type: ignore[method-assign]
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop == "time_limit"


def test_the_frontier_step_after_a_walk_stops_on_a_refusal(
    tmp_path: Path,
) -> None:
    """The step taken once the route ends is read at its own place.

    A sweep walks to the room holding an unwalked way, then steps through
    it. That second read is the one with no check before the deadline
    moved into the step itself, so a refusal there must still stop.
    """
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 6)
    clock = _Clock()
    session = _Session(_world(6), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=30.0, clock=clock,
    )
    # Five steps carry the route from the first room to the last, so the
    # sixth read is the frontier step and nothing else.
    executor._step = _refusing_after(executor, 5)  # type: ignore[method-assign]
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop == "time_limit"
    assert session.projector.current_place_id == "place:s:6:6", (
        "the walk finished, so the refusal was the frontier step"
    )


def test_the_live_frontier_step_stops_on_a_refusal(tmp_path: Path) -> None:
    """The third read, used when the stored map knows of no frontier."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = _evidence()
    for subject, predicate, value in (
        ("place:s:1:1", "title", "Room 1"),
        ("place:s:1:1", "exits", ["north"]),
        ("place:s:1:1", "exit.north", "place:s:2:2"),
        ("place:s:2:2", "title", "Room 2"),
        ("place:s:2:2", "exits", ["south"]),
        ("place:s:2:2", "exit.south", "place:s:1:1"),
    ):
        store.assert_fact(
            subject, predicate, value, layer="learned",
            confidence="confirmed", evidence=evidence, transaction_id="t1",
        )
    clock = _Clock()
    session = _Session({"place:s:1:1": {"east": "place:s:2:2"}},
                       "place:s:1:1", clock, 0.0)

    class _Room:
        exits = ("north", "east")

    session.observations.room = _Room()
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=30.0, clock=clock,
    )
    executor._step = _refusing_after(executor, 0)  # type: ignore[method-assign]
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop == "time_limit", (
        "the stored map holds no frontier, so this is the live-frontier read"
    )


# -- being cut off anyway -----------------------------------------------


def test_a_cancelled_sweep_records_its_stop_and_re_raises(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 6)
    clock = _Clock()
    session = _Session(_world(6), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=30.0, clock=clock,
    )
    real_step = executor._step
    walked = {"count": 0}

    async def _step(direction, expected, state, trace_id):
        if walked["count"] >= 2:
            raise asyncio.CancelledError()
        walked["count"] += 1
        return await real_step(direction, expected, state, trace_id)

    executor._step = _step  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(executor.sweep())
    store.close()

    stops = session.journal.kinds("routine_stop")
    assert len(stops) == 1
    assert stops[0]["stop"] == "cancelled"
    assert stops[0]["steps"] == 2, "the ground it covered is in the record"


def test_a_cut_in_the_first_step_still_records_a_stop(
    tmp_path: Path,
) -> None:
    """Covering no ground is not a reason to leave no trace."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 4)
    clock = _Clock()
    session = _Session(_world(4), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=30.0, clock=clock,
    )

    async def _step(direction, expected, state, trace_id):
        raise asyncio.CancelledError()

    executor._step = _step  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(executor.sweep())
    store.close()

    stops = session.journal.kinds("routine_stop")
    assert [stop["stop"] for stop in stops] == ["cancelled"]
    assert stops[0]["steps"] == 0


def test_a_cancelled_travel_records_its_stop_too(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 4)
    clock = _Clock()
    session = _Session(_world(4), "place:s:1:1", clock, 0.0)
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=30.0, clock=clock,
    )

    async def _step(direction, expected, state, trace_id):
        raise asyncio.CancelledError()

    executor._step = _step  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(executor.travel("Room 4"))
    store.close()

    stops = session.journal.kinds("routine_stop")
    assert [stop["stop"] for stop in stops] == ["cancelled"]
    assert stops[0]["destination"] == "Room 4"


def test_a_cut_while_a_command_is_in_flight_leaves_the_session_usable(
    tmp_path: Path,
) -> None:
    """The next call has to parse cleanly, or one cut poisons the run.

    The cut lands inside the wait for a reply, which is where a real one
    lands, since that is the only place a routine waits at all.
    """
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 4)
    clock = _Clock()
    session = _Session(_world(4), "place:s:1:1", clock, 0.0)
    real_command = session.command
    cut = {"done": False}

    async def _command(line, trace_id=None):
        if not cut["done"] and line in ("north", "south", "east", "west"):
            cut["done"] = True
            raise asyncio.CancelledError()
        return await real_command(line, trace_id)

    session.command = _command  # type: ignore[method-assign]
    executor = NavigationExecutor(
        session, store, {}, call_ceiling=30.0, clock=clock,
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(executor.sweep())

    assert session.journal.kinds("routine_stop")[0]["stop"] == "cancelled"

    # The session is asked for something new, exactly as the next call would.
    report = asyncio.run(executor.sweep())
    store.close()

    assert report.stop != "cancelled", "the session still answers"
    assert session.commands.count("north") >= 1


def test_every_routine_start_has_a_stop(tmp_path: Path) -> None:
    """The pairing a person checks in a run, checked here on the fakes."""
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    _corridor(store, 5)
    clock = _Clock()
    session = _Session(_world(5), "place:s:1:1", clock, 2.0)
    executor = NavigationExecutor(
        session, store, {"deadline_margin": 4.0},
        call_ceiling=12.0, clock=clock,
    )
    asyncio.run(executor.sweep())
    store.close()

    starts = session.journal.kinds("routine_start")
    stops = session.journal.kinds("routine_stop")
    assert len(starts) == len(stops) == 1


# -- what the model is told when routines cannot run --------------------


def test_a_missing_ceiling_refuses_navigation_and_names_the_key() -> None:
    settings = GatewaySettings(
        config_dir=Path("/nowhere"),
        capabilities={"navigation": True},
        call_ceiling=None,
    )
    reason = _navigation_refusal(settings)

    assert reason is not None
    assert "timeout" in reason
    assert GATEWAY_COMMAND in reason


def test_a_margin_wider_than_the_ceiling_refuses_navigation() -> None:
    """Otherwise every routine stops before its first step, quietly."""
    settings = GatewaySettings(
        config_dir=Path("/nowhere"),
        capabilities={"navigation": True},
        capability_settings={"navigation": {"deadline_margin": 45.0}},
        call_ceiling=30.0,
    )
    assert _navigation_refusal(settings) is not None


def test_a_negative_margin_refuses_navigation() -> None:
    """A minus sign would put the deadline past the ceiling, in silence.

    That is the overrun this whole bound exists to end, arriving back
    through configuration and reporting nothing wrong.
    """
    settings = GatewaySettings(
        config_dir=Path("/nowhere"),
        capabilities={"navigation": True},
        capability_settings={"navigation": {"deadline_margin": -5.0}},
        call_ceiling=30.0,
    )
    assert _navigation_refusal(settings) is not None


def test_a_margin_that_is_not_a_number_refuses_navigation() -> None:
    """Named, rather than a traceback out of the boot with no key in it."""
    settings = GatewaySettings(
        config_dir=Path("/nowhere"),
        capabilities={"navigation": True},
        capability_settings={"navigation": {"deadline_margin": "soon"}},
        call_ceiling=30.0,
    )
    reason = _navigation_refusal(settings)

    assert reason is not None
    assert "deadline_margin" in reason


def test_a_margin_that_compares_false_to_everything_refuses() -> None:
    """A NaN margin never fires the deadline, because nothing exceeds it."""
    settings = GatewaySettings(
        config_dir=Path("/nowhere"),
        capabilities={"navigation": True},
        capability_settings={"navigation": {"deadline_margin": float("nan")}},
        call_ceiling=30.0,
    )
    assert _navigation_refusal(settings) is not None


def test_a_margin_of_zero_refuses_navigation() -> None:
    """Zero leaves no room for the step already walking."""
    settings = GatewaySettings(
        config_dir=Path("/nowhere"),
        capabilities={"navigation": True},
        capability_settings={"navigation": {"deadline_margin": 0}},
        call_ceiling=30.0,
    )
    assert _navigation_refusal(settings) is not None


def test_a_usable_margin_is_not_refused() -> None:
    settings = GatewaySettings(
        config_dir=Path("/nowhere"),
        capabilities={"navigation": True},
        capability_settings={"navigation": {"deadline_margin": 4.0}},
        call_ceiling=30.0,
    )
    assert _navigation_refusal(settings) is None


def test_navigation_switched_off_is_never_refused() -> None:
    settings = GatewaySettings(
        config_dir=Path("/nowhere"),
        capabilities={"navigation": False},
        call_ceiling=None,
    )
    assert _navigation_refusal(settings) is None


def test_the_refusal_reaches_the_caller_as_capability_unavailable() -> None:
    """The code matters: the model reads it to know what it may retry.

    A settings error raised here would arrive as invalid arguments, which
    says the call was wrong rather than that the capability cannot run.
    """
    journal = _Journal()
    journal.since = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    surface = Surface(
        load_profile("direct-full"),
        extensions=frozenset({"sweep", "travel_to"}),
    )
    invocation = surface.resolve("sweep")
    reason = "navigation needs the agent's per-call timeout"

    async def _call():
        return await execute(
            _Session({}, "place:s:1:1"),
            invocation,
            surface,
            journal=journal,
            event_session="s1",
            navigation=None,
            navigation_refused=reason,
        )

    with pytest.raises(CapabilityUnavailable) as raised:
        asyncio.run(_call())
    assert reason in str(raised.value)

    result = failure(invocation.tool, raised.value, surface)
    assert result.code == "capability_unavailable"
    assert reason in result.message


# -- reading the ceiling from the settings file -------------------------


def _settings(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_ceiling_is_read_from_the_entry_that_spawns_the_gateway(
    tmp_path: Path,
) -> None:
    """The entry is found by its command, never by the name it was given."""
    path = _settings(tmp_path, """
mcp_servers:
  something_else:
    command: another-server
    timeout: 5
  renamed_from_mud:
    command: boukensha-gateway
    timeout: 30
""")
    assert _call_ceiling(path) == 30.0


def test_a_ceiling_stated_nowhere_reads_as_absent(tmp_path: Path) -> None:
    """Absent has to stay absent, so the caller can refuse rather than guess."""
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
""")
    assert _call_ceiling(path) is None


def test_a_ceiling_that_is_not_a_number_is_refused(tmp_path: Path) -> None:
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
    timeout: soon
""")
    with pytest.raises(GatewaySettingsError):
        _call_ceiling(path)


def test_a_ceiling_without_end_is_refused(tmp_path: Path) -> None:
    """An endless ceiling is no bound, so a routine has nothing to hold."""
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
    timeout: .inf
""")
    with pytest.raises(GatewaySettingsError):
        _call_ceiling(path)


def test_a_ceiling_that_is_not_a_number_at_all_is_refused(
    tmp_path: Path,
) -> None:
    """NaN parses as a float and would never compare true against one."""
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
    timeout: .nan
""")
    with pytest.raises(GatewaySettingsError):
        _call_ceiling(path)


def test_a_ceiling_of_zero_is_refused(tmp_path: Path) -> None:
    """Zero would make every routine stop before its first step."""
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
    timeout: 0
""")
    with pytest.raises(GatewaySettingsError):
        _call_ceiling(path)


def test_two_gateway_entries_that_agree_answer_the_question(
    tmp_path: Path,
) -> None:
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
    timeout: 30
  mud_readonly:
    command: /usr/local/bin/boukensha-gateway
    timeout: 30
""")
    assert _call_ceiling(path) == 30.0


def test_two_gateway_entries_written_differently_still_agree(
    tmp_path: Path,
) -> None:
    """The same number in two spellings is the same number."""
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
    timeout: 30
  mud_copy:
    command: boukensha-gateway
    timeout: "30.0"
""")
    assert _call_ceiling(path) == 30.0


def test_two_gateway_entries_that_disagree_are_refused(
    tmp_path: Path,
) -> None:
    """A running gateway cannot tell which entry started it.

    Taking the first would make the ceiling depend on the order the file
    happens to list, which is the silent wrong answer the command match
    was written to avoid.
    """
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
    timeout: 30
  mud_slow:
    command: boukensha-gateway
    timeout: 90
""")
    with pytest.raises(GatewaySettingsError):
        _call_ceiling(path)


def test_one_gateway_entry_stating_nothing_is_not_answered_by_another(
    tmp_path: Path,
) -> None:
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
  mud_other:
    command: boukensha-gateway
    timeout: 30
""")
    with pytest.raises(GatewaySettingsError):
        _call_ceiling(path)


def test_a_command_with_a_path_is_still_the_gateway(tmp_path: Path) -> None:
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: /opt/venv/bin/boukensha-gateway
    timeout: 25
""")
    assert _call_ceiling(path) == 25.0


def test_a_ceiling_written_as_text_still_reads_as_seconds(
    tmp_path: Path,
) -> None:
    """YAML quoting is a habit, not a statement about the number."""
    path = _settings(tmp_path, """
mcp_servers:
  mud:
    command: boukensha-gateway
    timeout: "30"
""")
    assert _call_ceiling(path) == 30.0


def test_the_shipped_settings_state_the_ceiling(tmp_path: Path) -> None:
    """The derivation needs a real key, and a comment is not one.

    An attempt's settings are rebuilt from this file by a YAML parse, which
    keeps no comments, so a commented ceiling could never reach a measured
    run even if the gateway looked for it.
    """
    root = Path(__file__).resolve().parents[3]
    shipped = root / ".boukensha" / "settings.yaml"
    assert shipped.is_file(), shipped
    assert _call_ceiling(shipped) is not None, (
        "settings.yaml must state 'timeout' on the gateway's mcp_servers "
        "entry, or navigation refuses to run"
    )
