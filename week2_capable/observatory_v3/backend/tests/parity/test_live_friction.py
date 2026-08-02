from types import SimpleNamespace

from mud_gateway.journal import Event

from observatory_v3_backend.projections.live import _friction


def event(sequence: int, kind: str, payload: dict[str, object]) -> Event:
    return Event(
        seq=sequence,
        session="gateway-1",
        at=float(sequence),
        monotonic=float(sequence),
        kind=kind,
        payload=payload,
    )


def iteration_event(number: int) -> dict[str, object]:
    return {
        "phase": "iteration",
        "n": number,
        "at": f"1970-01-01T00:00:{number:02d}+00:00",
    }


def test_live_confusion_loop_uses_recorded_session_threshold_and_evidence():
    events = [event(1, "position", {"place": 7})] + [
        event(sequence, "command", {"line": "east"}) for sequence in range(2, 7)
    ]

    diagnostic = _friction(
        events,
        iterations=6,
        iteration_events=[iteration_event(number) for number in range(1, 7)],
        world=SimpleNamespace(nodes=(object(), object())),
    )

    assert diagnostic.kind == "confusion_loop"
    assert diagnostic.repeated_command == "east"
    assert diagnostic.repeated_count == 5
    assert diagnostic.evidence == (2, 3, 4, 5, 6)
    assert diagnostic.new_places == 1
    assert diagnostic.window_iterations == 6
    assert diagnostic.iterations_since_new_place == 5
    assert diagnostic.threshold == "same command recorded at least five times"


def test_live_progress_stall_uses_recorded_session_ratio():
    events = [event(4, "position", {"place": 1})]

    diagnostic = _friction(
        events,
        iterations=10,
        iteration_events=[iteration_event(number) for number in range(1, 11)],
        world=SimpleNamespace(nodes=(object(),)),
    )

    assert diagnostic.kind == "progress_stall"
    assert diagnostic.distinct_places == 1
    assert diagnostic.evidence == (4,)
    assert diagnostic.threshold == (
        "ten or more iterations per distinct observed place"
    )
    assert diagnostic.new_places == 1
    assert diagnostic.window_iterations == 10
    assert diagnostic.iterations_since_new_place == 6


def test_live_friction_stays_clear_below_both_thresholds():
    events = [event(1, "position", {"place": 3})] + [
        event(sequence, "command", {"line": "north"}) for sequence in range(2, 6)
    ]

    diagnostic = _friction(
        events,
        iterations=9,
        iteration_events=[],
        world=SimpleNamespace(nodes=(object(),)),
    )

    assert diagnostic.kind is None
    assert diagnostic.repeated_count == 4
    assert diagnostic.evidence == ()


def test_live_progress_counts_new_places_in_the_last_ten_iterations():
    events = [
        event(2, "position", {"place": 1}),
        event(8, "position", {"place": 2}),
        event(13, "position", {"place": 3}),
        event(18, "position", {"place": 4}),
    ]
    iteration_events = [iteration_event(number) for number in range(1, 19)]

    diagnostic = _friction(
        events,
        iterations=18,
        iteration_events=iteration_events,
        world=SimpleNamespace(nodes=tuple(object() for _ in range(4))),
    )

    assert diagnostic.new_places == 2
    assert diagnostic.window_iterations == 10
    assert diagnostic.iterations_since_new_place == 0


def test_repeated_command_count_is_scoped_to_the_current_room():
    events = [
        event(1, "position", {"place": 1}),
        event(2, "command", {"line": "east"}),
        event(3, "command", {"line": "east"}),
        event(4, "position", {"place": 2}),
        event(5, "command", {"line": "north"}),
        event(6, "command", {"line": "north"}),
    ]

    diagnostic = _friction(
        events,
        iterations=4,
        iteration_events=[],
        world=SimpleNamespace(nodes=(object(), object())),
    )

    assert diagnostic.repeated_command == "north"
    assert diagnostic.repeated_count == 2
