from __future__ import annotations

import fcntl
import sqlite3
from pathlib import Path

import pytest

from mud_gateway.knowledge import (
    EvidenceRef,
    KnowledgeError,
    KnowledgeInput,
    KnowledgeStore,
)


def evidence(
    session: str,
    seq: int,
    *,
    parser: str = "rules-1",
    observed_at: float | None = None,
) -> EvidenceRef:
    return EvidenceRef(
        session_id=session,
        source_seq=seq,
        wire_digest=f"wire-{session}-{seq}",
        parser_version=parser,
        method="test-rule",
        observed_at=float(seq if observed_at is None else observed_at),
    )


def test_cdc_is_global_while_source_sequences_remain_provenance(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    store.assert_fact(
        "player:alpha",
        "state.gold",
        10,
        layer="parsed",
        confidence="high",
        evidence=evidence("session-z", 90),
    )
    store.assert_fact(
        "player:alpha",
        "state.level",
        2,
        layer="parsed",
        confidence="high",
        evidence=evidence("session-a", 1),
    )

    changes = store.changes_since()
    assert [change.change_seq for change in changes] == [1, 2]
    assert [(change.session_id, change.source_seq) for change in changes] == [
        ("session-z", 90),
        ("session-a", 1),
    ]


def test_repeated_value_adds_support_without_duplicate_current_fact(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    first = store.assert_fact(
        "player:alpha",
        "state.posture",
        "standing",
        layer="parsed",
        confidence="high",
        evidence=evidence("s1", 1),
    )
    second = store.assert_fact(
        "player:alpha",
        "state.posture",
        "standing",
        layer="parsed",
        confidence="high",
        evidence=evidence("s2", 1),
    )

    assert second.assertion_id == first.assertion_id
    assert second.evidence.session_id == "s1"
    assert second.latest_evidence.session_id == "s2"
    assert [change.operation for change in store.changes_since()] == [
        "assert",
        "support",
    ]
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_refs"
        ).fetchone()[0] == 2


def test_duplicate_projection_of_the_same_wire_evidence_is_idempotent(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    source = evidence("s1", 1)
    first = store.assert_fact(
        "player:alpha",
        "state.hit",
        20,
        layer="parsed",
        confidence="high",
        evidence=source,
    )
    second = store.assert_fact(
        "player:alpha",
        "state.hit",
        20,
        layer="parsed",
        confidence="high",
        evidence=source,
    )

    assert second.assertion_id == first.assertion_id
    assert store.last_change_seq() == 1


def test_parsed_state_appends_and_supersedes_each_value_change(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    assertion_ids = []
    for seq, hit in enumerate((20, 18, 20), start=1):
        assertion_ids.append(
            store.assert_fact(
                "player:alpha",
                "state.hit",
                hit,
                layer="parsed",
                confidence="high",
                evidence=evidence("s1", seq),
            ).assertion_id
        )

    current = store.current_facts(layer="parsed")[0]
    assert current.value == 20
    assert current.assertion_id == assertion_ids[-1]
    assert len(set(assertion_ids)) == 3
    assert [change.operation for change in store.changes_since()] == [
        "assert",
        "supersede",
        "supersede",
    ]
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM assertions"
        ).fetchone()[0] == 3


def test_contradictions_coexist_until_explicit_resolution(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    first = store.assert_fact(
        "room:r1",
        "exit.north",
        "room:r2",
        layer="learned",
        confidence="medium",
        evidence=evidence("s1", 3),
    )
    conflict = store.assert_fact(
        "room:r1",
        "exit.north",
        "room:r9",
        layer="learned",
        confidence="medium",
        evidence=evidence("s2", 8),
    )

    assert first.status == "active"
    assert conflict.status == "conflicted"
    assert conflict.conflict_group
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT supersedes FROM assertions WHERE assertion_id = ?",
            (conflict.assertion_id,),
        ).fetchone()[0] == first.assertion_id
    assert store.current_facts(layer="learned")[0].assertion_id == first.assertion_id

    supported = store.assert_fact(
        "room:r1",
        "exit.north",
        "room:r9",
        layer="learned",
        confidence="high",
        evidence=evidence("s2", 9),
    )
    assert supported.assertion_id == conflict.assertion_id
    assert supported.latest_evidence.source_seq == 9

    store.resolve(first.fact_id, conflict.assertion_id, reason="verified traversal")
    assert store.current_facts(layer="learned")[0].assertion_id == conflict.assertion_id
    assert store.changes_since()[-1].operation == "resolve"


def test_snapshot_reset_and_restore_append_history(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    original = store.assert_fact(
        "room:r1",
        "title",
        "The Bakery",
        layer="learned",
        confidence="high",
        evidence=evidence("s1", 5),
    )
    snapshot = store.snapshot("before baseline reset")
    assert store.verify_snapshot(snapshot.snapshot_id) is True
    retracted = store.reset_learned(
        reason="level1-temple@1",
        snapshot_id=snapshot.snapshot_id,
    )

    assert retracted == 1
    assert store.current_facts(layer="learned") == []
    restored = store.restore(snapshot.snapshot_id, reason="operator restore")
    assert restored == 1
    current = store.current_facts(layer="learned")
    assert current[0].value == "The Bakery"
    assert current[0].assertion_id != original.assertion_id
    with sqlite3.connect(store.path) as connection:
        restore = connection.execute(
            "SELECT snapshot_id, assertions FROM restores"
        ).fetchone()
        assert restore == (snapshot.snapshot_id, 1)
        reset = connection.execute(
            "SELECT snapshot_id, assertions FROM knowledge_resets"
        ).fetchone()
        assert reset == (snapshot.snapshot_id, 1)
    assert [change.operation for change in store.changes_since()] == [
        "assert",
        "snapshot",
        "retract",
        "assert",
    ]


def test_snapshot_verification_detects_assertion_content_tampering(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    assertion = store.assert_fact(
        "room:r1",
        "title",
        "The Bakery",
        layer="learned",
        confidence="high",
        evidence=evidence("s1", 1),
    )
    snapshot = store.snapshot("before mutation")
    store.close()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE assertions SET value_digest = ? WHERE assertion_id = ?",
            ("tampered", assertion.assertion_id),
        )

    reopened = KnowledgeStore(store.path, player_id="alpha")
    try:
        assert reopened.verify_snapshot(snapshot.snapshot_id) is False
    finally:
        reopened.close()


def test_restore_selects_snapshot_value_over_later_learned_resolution(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    original = store.assert_fact(
        "room:r1",
        "title",
        "The Bakery",
        layer="learned",
        confidence="high",
        evidence=evidence("s1", 1),
    )
    snapshot = store.snapshot("known good")
    changed = store.assert_fact(
        "room:r1",
        "title",
        "The Ruins",
        layer="learned",
        confidence="high",
        evidence=evidence("s2", 1),
    )
    store.resolve(original.fact_id, changed.assertion_id, reason="later evidence")

    store.restore(snapshot.snapshot_id, reason="operator rollback")

    restored = store.current_facts(layer="learned")[0]
    assert restored.value == "The Bakery"
    assert restored.assertion_id not in {
        original.assertion_id,
        changed.assertion_id,
    }
    assert store.changes_since()[-1].operation == "supersede"


def test_rebuild_records_new_parser_version_in_caller_order(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    old = store.assert_fact(
        "room:r1",
        "title",
        "First",
        layer="learned",
        confidence="high",
        evidence=evidence("legacy-session", 1, parser="rules-1"),
    )
    rebuild_id = store.rebuild(
        [
            KnowledgeInput(
                "room:r1",
                "title",
                "First",
                "learned",
                "high",
                evidence("later-session", 4, observed_at=20),
            ),
            KnowledgeInput(
                "room:r2",
                "title",
                "Second",
                "learned",
                "high",
                evidence("earlier-session", 99, observed_at=30),
            ),
        ],
        parser_version="rules-2",
        session_order={"earlier-session": 0, "later-session": 1},
    )

    assert rebuild_id
    assert [fact.evidence.parser_version for fact in store.current_facts()] == [
        "rules-2",
        "rules-2",
    ]
    assert store.current_facts()[0].assertion_id != old.assertion_id
    rebuild_changes = [
        change
        for change in store.changes_since()
        if change.session_id in {"earlier-session", "later-session"}
    ]
    assert [change.session_id for change in rebuild_changes] == [
        "earlier-session",
        "later-session",
    ]
    assert store.changes_since()[-1].operation == "rebuild"


def test_read_only_consumer_cannot_write(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.db"
    writer = KnowledgeStore(path, player_id="alpha")
    writer.assert_fact(
        "player:alpha",
        "state.gold",
        7,
        layer="parsed",
        confidence="high",
        evidence=evidence("s1", 1),
    )
    writer.close()

    reader = KnowledgeStore(path, player_id="alpha", read_only=True)
    assert reader.current_facts()[0].value == 7
    with pytest.raises(KnowledgeError, match="read-only"):
        reader.assert_fact(
            "player:alpha",
            "state.gold",
            8,
            layer="parsed",
            confidence="high",
            evidence=evidence("s1", 2),
        )


def test_one_writer_lock_allows_concurrent_readers(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.db"
    writer = KnowledgeStore(path, player_id="alpha")
    try:
        with pytest.raises(KnowledgeError, match="already has a writer"):
            KnowledgeStore(path, player_id="alpha")
        reader = KnowledgeStore(path, player_id="alpha", read_only=True)
        reader.close()
    finally:
        writer.close()


def test_schema_failure_releases_writer_lock(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=99")

    with pytest.raises(KnowledgeError, match="unsupported"):
        KnowledgeStore(path, player_id="alpha")

    with path.with_name("knowledge.db.writer.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def test_read_only_consumer_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=99")

    with pytest.raises(KnowledgeError, match="unsupported"):
        KnowledgeStore(path, player_id="alpha", read_only=True)


def test_store_refuses_a_different_player_identity(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.db"
    owner = KnowledgeStore(path, player_id="alpha")
    owner.close()

    with pytest.raises(KnowledgeError, match="belongs to player 'alpha'"):
        KnowledgeStore(path, player_id="beta")
    with pytest.raises(KnowledgeError, match="belongs to player 'alpha'"):
        KnowledgeStore(path, player_id="beta", read_only=True)


def test_restore_is_atomic_when_one_assertion_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="alpha")
    for predicate, value in (("title", "Bakery"), ("zone", "Midgaard")):
        store.assert_fact(
            "room:r1",
            predicate,
            value,
            layer="learned",
            confidence="high",
            evidence=evidence("s1", 1),
        )
    snapshot = store.snapshot("before reset")
    store.reset_learned(reason="test", snapshot_id=snapshot.snapshot_id)
    before = store.last_change_seq()
    original = store._assert_fact
    calls = 0

    def fail_second(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KnowledgeError("injected restore failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "_assert_fact", fail_second)
    with pytest.raises(KnowledgeError, match="injected"):
        store.restore(snapshot.snapshot_id, reason="test")

    assert store.current_facts(layer="learned") == []
    assert store.last_change_seq() == before


def test_two_players_isolate_facts_cdc_snapshots_and_reset(
    tmp_path: Path,
) -> None:
    alpha = KnowledgeStore(
        tmp_path / "profiles" / "alpha" / "knowledge.db",
        player_id="alpha",
    )
    beta = KnowledgeStore(
        tmp_path / "profiles" / "beta" / "knowledge.db",
        player_id="beta",
    )
    try:
        alpha.assert_fact(
            "room:alpha-canary",
            "title",
            "Alpha only",
            layer="learned",
            confidence="high",
            evidence=evidence("alpha-session", 1),
        )
        beta.assert_fact(
            "room:beta-canary",
            "title",
            "Beta only",
            layer="learned",
            confidence="high",
            evidence=evidence("beta-session", 1),
        )
        snapshot = alpha.snapshot("alpha reset")
        alpha.reset_learned(
            reason="level1-temple@1",
            snapshot_id=snapshot.snapshot_id,
        )

        assert alpha.current_facts(layer="learned") == []
        assert [fact.value for fact in beta.current_facts(layer="learned")] == [
            "Beta only"
        ]
        assert alpha.last_change_seq() == 3
        assert beta.last_change_seq() == 1
        assert beta.get_snapshot(snapshot.snapshot_id) is None
    finally:
        alpha.close()
        beta.close()
