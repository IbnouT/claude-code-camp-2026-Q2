"""The room identity rule: which observed places are one room."""

from __future__ import annotations

from mud_gateway.identity import (
    CORROBORATED,
    Place,
    UNCONTESTED,
    resolve,
)
import pytest


def _place(place_id, session, title, exits, digest="d", links=None) -> Place:
    return Place(
        place_id=place_id,
        session=session,
        title=title,
        exits=tuple(sorted(exits)),
        description_digest=digest,
        links=dict(links or {}),
    )


def _rooms(bindings) -> dict[str, str]:
    return {binding.place_id: binding.room_id for binding in bindings}


def test_the_same_room_seen_in_two_sessions_becomes_one_room() -> None:
    places = [
        _place("place:s1:1:1", "s1", "The Armory", ["north"]),
        _place("place:s2:1:1", "s2", "The Armory", ["north"]),
    ]
    rooms = _rooms(resolve(places))
    assert rooms["place:s1:1:1"] == rooms["place:s2:1:1"]


def test_a_maze_of_identical_rooms_stays_separate() -> None:
    """Seven forest rooms share title, exits and description in one run.

    Only where their exits lead tells them apart, so nothing merges them.
    """
    places = [
        _place(f"place:s1:{n}:1", "s1", "In The Dense Forest", ["north", "south"])
        for n in range(1, 8)
    ]
    rooms = _rooms(resolve(places))
    assert len(set(rooms.values())) == 7


def test_a_contradicting_exit_blocks_a_merge() -> None:
    """Same key, but north leads to places that are themselves distinct."""
    places = [
        _place("place:s1:1:1", "s1", "Main Street", ["north"],
               links={"north": "place:s1:2:1"}),
        _place("place:s2:1:1", "s2", "Main Street", ["north"],
               links={"north": "place:s2:2:1"}),
        _place("place:s1:2:1", "s1", "The Bakery", ["south"], digest="a"),
        _place("place:s2:2:1", "s2", "The Butcher", ["south"], digest="b"),
    ]
    rooms = _rooms(resolve(places))
    assert rooms["place:s1:1:1"] != rooms["place:s2:1:1"]


def test_a_corroborating_exit_merges_and_is_confirmed() -> None:
    """North leads to the same room from both, so both are that room."""
    places = [
        _place("place:s1:1:1", "s1", "Main Street", ["north"],
               links={"north": "place:s1:2:1"}),
        _place("place:s2:1:1", "s2", "Main Street", ["north"],
               links={"north": "place:s2:2:1"}),
        _place("place:s1:2:1", "s1", "The Bakery", ["south"], digest="a"),
        _place("place:s2:2:1", "s2", "The Bakery", ["south"], digest="a"),
    ]
    bindings = resolve(places)
    rooms = _rooms(bindings)
    assert rooms["place:s1:1:1"] == rooms["place:s2:1:1"]
    support = {b.place_id: b.confidence for b in bindings}
    assert support["place:s2:1:1"] == CORROBORATED


def test_a_hub_seen_twice_in_one_session_can_still_be_one_room() -> None:
    """The tracker re-mints a place when it loses track, so duplicates happen.

    Nothing contradicts these two, and a shared exit agrees, so the hub
    does not stay split.
    """
    places = [
        _place("place:s1:1:1", "s1", "Temple Square", ["north"],
               links={"north": "place:s1:9:1"}),
        _place("place:s1:5:1", "s1", "Temple Square", ["north"],
               links={"north": "place:s1:9:1"}),
        _place("place:s1:9:1", "s1", "The Temple", ["south"], digest="t"),
    ]
    rooms = _rooms(resolve(places))
    assert rooms["place:s1:1:1"] == rooms["place:s1:5:1"]


def test_different_descriptions_are_different_rooms() -> None:
    places = [
        _place("place:s1:1:1", "s1", "Main Street", ["north"], digest="a"),
        _place("place:s2:1:1", "s2", "Main Street", ["north"], digest="b"),
    ]
    rooms = _rooms(resolve(places))
    assert rooms["place:s1:1:1"] != rooms["place:s2:1:1"]


def test_resolving_twice_gives_the_same_bindings() -> None:
    places = [
        _place("place:s1:1:1", "s1", "The Armory", ["north"]),
        _place("place:s2:1:1", "s2", "The Armory", ["north"]),
        _place("place:s3:1:1", "s3", "Market Square", ["south", "west"]),
    ]
    assert resolve(places) == resolve(places)


def test_an_unbound_place_still_gets_a_room_of_its_own() -> None:
    places = [_place("place:s1:1:1", "s1", "A Lonely Cave", ["out"])]
    bindings = resolve(places)
    assert len(bindings) == 1
    assert bindings[0].confidence == UNCONTESTED


def _chain(session, titles, first_dirs, back_dirs):
    """A walked chain of same-key rooms, linked in the order visited."""
    places = []
    for n, (title, forward) in enumerate(zip(titles, first_dirs), start=1):
        links = {}
        if n < len(titles):
            links[forward] = f"place:{session}:{n + 1}:1"
        if n > 1:
            links[back_dirs[n - 2]] = f"place:{session}:{n - 1}:1"
        places.append(
            _place(f"place:{session}:{n}:1", session, title,
                   ["north", "south", "east", "west"], links=links)
        )
    return places


def test_two_sessions_walking_a_maze_differently_do_not_merge() -> None:
    """The real failure case: same title, exits and description everywhere.

    One run walks east, east, north. Another walks east, north, east. The
    rooms they end in are different rooms, and nothing may glue them.
    """
    title = "In The Dense Forest Between The Hills"
    a = _chain("s1", [title] * 4, ["east", "east", "north", ""],
               ["west", "west", "south"])
    b = _chain("s2", [title] * 4, ["east", "north", "east", ""],
               ["west", "south", "west"])
    rooms = _rooms(resolve(a + b))

    assert rooms["place:s1:4:1"] != rooms["place:s2:4:1"]
    assert rooms["place:s1:3:1"] != rooms["place:s2:3:1"]


def test_renaming_sessions_does_not_change_the_rooms() -> None:
    """Identity may not depend on the accident of a session identifier."""
    def world(first, second):
        return [
            _place(f"place:{first}:1:1", first, "Market Square", ["north"]),
            _place(f"place:{second}:1:1", second, "Market Square", ["north"]),
            _place(f"place:{first}:2:1", first, "A Quiet Lane", ["south"],
                   digest="q"),
            _place(f"place:{second}:2:1", second, "A Quiet Lane", ["south"],
                   digest="q"),
        ]

    def shape(bindings):
        groups = {}
        for binding in bindings:
            groups.setdefault(binding.room_id, set()).add(
                binding.place_id.split(":")[2]
            )
        return sorted(sorted(members) for members in groups.values())

    assert shape(resolve(world("aaa", "bbb"))) == shape(
        resolve(world("zzz", "yyy"))
    )


def test_contradicting_evidence_arriving_later_splits_a_merge() -> None:
    """A merge made before its evidence existed must be revised, not kept."""
    without_links = [
        _place("place:s1:1:1", "s1", "Main Street", ["north"]),
        _place("place:s2:1:1", "s2", "Main Street", ["north"]),
    ]
    joined = _rooms(resolve(without_links))
    assert joined["place:s1:1:1"] == joined["place:s2:1:1"]

    with_links = [
        _place("place:s1:1:1", "s1", "Main Street", ["north"],
               links={"north": "place:s1:2:1"}),
        _place("place:s2:1:1", "s2", "Main Street", ["north"],
               links={"north": "place:s2:2:1"}),
        _place("place:s1:2:1", "s1", "The Bakery", ["south"], digest="a"),
        _place("place:s2:2:1", "s2", "The Forge", ["south"], digest="b"),
    ]
    split = _rooms(resolve(with_links))
    assert split["place:s1:1:1"] != split["place:s2:1:1"]


def test_a_run_that_does_not_settle_says_so() -> None:
    """Silently returning a half-resolved answer is not allowed."""
    places = [
        _place("place:s1:1:1", "s1", "The Armory", ["north"]),
        _place("place:s2:1:1", "s2", "The Armory", ["north"]),
    ]
    with pytest.raises(ValueError):
        resolve(places, max_rounds=0)


def _glue_world(first, second, third):
    """Two contradicting places and a partly observed one between them.

    P1 and P3 disagree about north. P2 only ever walked east, to a place
    both of them also reached, so it agrees with each of them. Nothing
    may glue P1 to P3 through P2.
    """
    return [
        _place(f"place:{first}:1:1", first, "Main Street", ["north", "east"],
               links={"north": f"place:{first}:2:1",
                      "east": f"place:{first}:3:1"}),
        _place(f"place:{second}:1:1", second, "Main Street", ["north", "east"],
               links={"east": f"place:{second}:3:1"}),
        _place(f"place:{third}:1:1", third, "Main Street", ["north", "east"],
               links={"north": f"place:{third}:2:1",
                      "east": f"place:{third}:3:1"}),
        _place(f"place:{first}:2:1", first, "The Bakery", ["south"], digest="a"),
        _place(f"place:{third}:2:1", third, "The Butcher", ["south"], digest="b"),
        _place(f"place:{first}:3:1", first, "The Fountain", ["west"], digest="f"),
        _place(f"place:{second}:3:1", second, "The Fountain", ["west"], digest="f"),
        _place(f"place:{third}:3:1", third, "The Fountain", ["west"], digest="f"),
    ]


def test_a_partly_observed_place_cannot_glue_two_that_disagree() -> None:
    for names in (
        ("aaa", "bbb", "ccc"),
        ("ccc", "bbb", "aaa"),
        ("bbb", "aaa", "ccc"),
        ("zzz", "aaa", "mmm"),
    ):
        first, second, third = names
        rooms = _rooms(resolve(_glue_world(first, second, third)))
        assert (
            rooms[f"place:{first}:1:1"] != rooms[f"place:{third}:1:1"]
        ), f"P1 and P3 were glued together under naming {names}"


def test_a_conflicting_neighbourhood_resolves_the_same_way_when_renamed() -> None:
    def shape(bindings, names):
        roles = {
            f"place:{names[0]}:1:1": "P1",
            f"place:{names[1]}:1:1": "P2",
            f"place:{names[2]}:1:1": "P3",
        }
        groups = {}
        for binding in bindings:
            role = roles.get(binding.place_id)
            if role is not None:
                groups.setdefault(binding.room_id, set()).add(role)
        return sorted(sorted(members) for members in groups.values())

    first = ("aaa", "bbb", "ccc")
    second = ("zzz", "yyy", "xxx")
    assert shape(resolve(_glue_world(*first)), first) == shape(
        resolve(_glue_world(*second)), second
    )


def test_lookalikes_one_hop_above_a_contradiction_stay_apart() -> None:
    """A and C look alike, and so do their neighbours X and Y.

    But X and Y are proven different by where they lead, so A and C are
    different too, one hop above the contradiction.
    """
    places = [
        _place("place:s1:1:1", "s1", "Main Street", ["north"],
               links={"north": "place:s1:2:1"}),
        _place("place:s2:1:1", "s2", "Main Street", ["north"],
               links={"north": "place:s2:2:1"}),
        _place("place:s1:2:1", "s1", "Side Alley", ["north"], digest="x",
               links={"north": "place:s1:3:1"}),
        _place("place:s2:2:1", "s2", "Side Alley", ["north"], digest="x",
               links={"north": "place:s2:3:1"}),
        _place("place:s1:3:1", "s1", "The Bakery", ["south"], digest="a"),
        _place("place:s2:3:1", "s2", "The Butcher", ["south"], digest="b"),
    ]
    bindings = resolve(places)
    rooms = _rooms(bindings)

    assert rooms["place:s1:2:1"] != rooms["place:s2:2:1"]
    assert rooms["place:s1:1:1"] != rooms["place:s2:1:1"]
    labels = {b.place_id: b.confidence for b in bindings}
    assert labels["place:s1:1:1"] == UNCONTESTED


def test_identity_is_recorded_and_recomputed(tmp_path) -> None:
    """Recording replaces what was there, so a recompute never accretes."""
    from mud_gateway.identity import record, rooms_of
    from mud_gateway.knowledge import KnowledgeStore
    from mud_gateway.knowledge_models import EvidenceRef

    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = EvidenceRef(
        session_id="s1", source_seq=1, wire_digest="d" * 64,
        parser_version="1", method="test", observed_at=1.0,
    )
    for subject, predicate, value in (
        ("place:s1:1:1", "title", "The Armory"),
        ("place:s1:1:1", "exits", ["north"]),
        ("place:s2:1:1", "title", "The Armory"),
        ("place:s2:1:1", "exits", ["north"]),
    ):
        store.assert_fact(
            subject, predicate, value, layer="learned",
            confidence="confirmed", evidence=evidence, transaction_id="t1",
        )

    first = record(store, store.current_facts(layer="learned"))
    assert first["place:s1:1:1"] == first["place:s2:1:1"]
    assert rooms_of(store) == first

    again = record(store, store.current_facts(layer="learned"))
    assert rooms_of(store) == again
    assert len(rooms_of(store)) == 2
    store.close()


def test_recorded_identity_never_touches_the_learned_layer(tmp_path) -> None:
    from mud_gateway.identity import record
    from mud_gateway.knowledge import KnowledgeStore
    from mud_gateway.knowledge_models import EvidenceRef

    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = EvidenceRef(
        session_id="s1", source_seq=1, wire_digest="d" * 64,
        parser_version="1", method="test", observed_at=1.0,
    )
    store.assert_fact(
        "place:s1:1:1", "title", "The Armory", layer="learned",
        confidence="confirmed", evidence=evidence, transaction_id="t1",
    )
    before = {
        (a.subject, a.predicate, a.value)
        for a in store.current_facts(layer="learned")
    }
    record(store, store.current_facts(layer="learned"))
    after = {
        (a.subject, a.predicate, a.value)
        for a in store.current_facts(layer="learned")
    }
    assert before == after
    store.close()


def test_a_withdrawn_fact_returns_when_it_is_observed_again(tmp_path) -> None:
    """Re-observing a retracted fact must restore it, not just note it.

    Adding evidence to the assertion that was withdrawn would leave the
    fact absent from the store while looking recorded.
    """
    from mud_gateway.knowledge import KnowledgeStore
    from mud_gateway.knowledge_models import EvidenceRef

    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = EvidenceRef(
        session_id="s1", source_seq=1, wire_digest="d" * 64,
        parser_version="1", method="test", observed_at=1.0,
    )
    store.assert_fact(
        "place:s1:1:1", "title", "The Armory", layer="derived",
        confidence="tracked", evidence=evidence, transaction_id="t1",
    )
    store.retract_layer("derived", reason="test")
    assert store.current_facts(layer="derived") == []

    store.assert_fact(
        "place:s1:1:1", "title", "The Armory", layer="derived",
        confidence="tracked", evidence=evidence, transaction_id="t2",
    )
    current = store.current_facts(layer="derived")
    assert [(a.subject, a.value) for a in current] == [
        ("place:s1:1:1", "The Armory")
    ]
    store.close()
