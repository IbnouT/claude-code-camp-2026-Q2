"""Disposable index identity, atomicity, boundedness, and search gates."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest

from observatory_v3_backend.index import (
    EntityKind,
    IndexCorruptionError,
    IndexStore,
    IndexWriterUnavailableError,
    SessionIndexProjector,
    UnsupportedIndexSchemaError,
    stable_entity_id,
)
from observatory_v3_backend.index.projector import IndexBuildError
from observatory_v3_backend.index.schema import INDEX_SCHEMA_VERSION
from observatory_v3_backend.index.store import CatalogCursor
from observatory_v3_backend.repositories import RegistryDatabase

from .fixtures import RetainedFixture, build_retained_fixture


def test_identity_contract_examples_are_exact() -> None:
    expected = {
        ("session", "registry:session-000"): (
            "obs1_session_c9a4fe2ceb8059faaa27501347780400"
        ),
        ("goal", "agent:1:initial"): ("obs1_goal_19f6dc0153ed53ecbb0de56d5f012673"),
        ("goal", "operator:goal-1:revise"): (
            "obs1_goal_df44b85d5f43561bb36bf08787045c98"
        ),
        ("nudge", "operator:nudge-1:guide"): (
            "obs1_nudge_a6f47210541a5db4b82a1e3dc50e74a4"
        ),
        ("turn", "agent:2"): ("obs1_turn_6e934d3e47e05b8d8c3d76367e0046f6"),
        ("iteration", "agent:3"): ("obs1_iteration_9b654f7a9829567c91b6583a8d2d13ef"),
        ("record", "agent:4"): ("obs1_record_156b56a530a05c829945f02b4522e696"),
        ("record", "gateway:gateway-000:7"): (
            "obs1_record_a8dc0c0310e2553ea510b7be3ef47f46"
        ),
        ("trace", "gateway:gateway-000:trace:trace-1"): (
            "obs1_trace_a5303451fa3e527b9ce7b28bc866bea2"
        ),
        ("experiment_sample", "experiment:job-1:run:sample-1"): (
            "obs1_experiment_sample_ecc0e530fcda5dda9aea4fdb34935d23"
        ),
    }

    for (kind, anchor), entity_id in expected.items():
        assert (
            stable_entity_id("session-000", cast(EntityKind, kind), anchor) == entity_id
        )


def test_index_creation_permissions_and_single_writer(tmp_path: Path) -> None:
    source = tmp_path / "runtime" / "observatory" / "index-v1.sqlite3"

    with IndexStore(source):
        assert source.stat().st_mode & 0o777 == 0o600
        assert source.parent.stat().st_mode & 0o777 == 0o700
        assert source.with_suffix(".sqlite3.lock").stat().st_mode & 0o777 == 0o600
        with pytest.raises(IndexWriterUnavailableError):
            IndexStore(source)


def test_unknown_and_corrupt_indexes_require_explicit_recreation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "observatory" / "index-v1.sqlite3"
    source.parent.mkdir(parents=True)
    with sqlite3.connect(source) as database:
        database.execute("PRAGMA user_version=99")
    with pytest.raises(UnsupportedIndexSchemaError):
        IndexStore(source)

    with IndexStore.recreate(source):
        with sqlite3.connect(source) as database:
            assert (
                database.execute("PRAGMA user_version").fetchone()[0]
                == INDEX_SCHEMA_VERSION
            )

    source.write_bytes(b"not a sqlite database")
    with pytest.raises(IndexCorruptionError):
        IndexStore(source)
    with IndexStore.recreate(source):
        assert source.is_file()


def test_schema_one_watermarks_migrate_without_discarding_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "observatory" / "index-v1.sqlite3"
    source.parent.mkdir(parents=True)
    with sqlite3.connect(source) as database:
        database.execute(
            """
            CREATE TABLE source_watermarks (
                session_id TEXT PRIMARY KEY,
                registry_updated_at TEXT NOT NULL,
                lifecycle_sequence INTEGER NOT NULL,
                gateway_session_id TEXT NOT NULL,
                gateway_sequence INTEGER NOT NULL,
                agent_source_id TEXT NOT NULL,
                agent_offset INTEGER NOT NULL,
                agent_next_line INTEGER NOT NULL,
                operator_source_id TEXT NOT NULL,
                operator_revision TEXT NOT NULL,
                experiment_revision TEXT
            )
            """
        )
        database.execute("PRAGMA user_version=1")

    with IndexStore(source):
        with sqlite3.connect(source) as database:
            assert (
                database.execute("PRAGMA user_version").fetchone()[0]
                == INDEX_SCHEMA_VERSION
            )
            columns = {
                str(row[1])
                for row in database.execute("PRAGMA table_info(source_watermarks)")
            }
    assert {
        "gateway_source_id",
        "knowledge_revision",
        "operator_message_count",
        "operator_history_digest",
        "operator_state",
    } <= columns


def test_rebuild_is_deterministic_append_stable_and_experiment_linked(
    tmp_path: Path,
) -> None:
    fixture = _rich_fixture(tmp_path)
    source = tmp_path / "index-v1.sqlite3"
    registry = RegistryDatabase(fixture.config_dir)

    with IndexStore(source) as index:
        projector = SessionIndexProjector(registry, index)
        assert projector.rebuild(fixture.selected_session_id) == 1
        first = index.canonical_session_rows(fixture.selected_session_id)
        first_ids = _entity_ids(first)

        _append_agent_record(
            fixture.selected_session_dir,
            {
                "phase": "reasoning",
                "text": "Look behind the fountain",
                "at": "2026-08-01T00:00:08+00:00",
            },
        )
        assert projector.rebuild(fixture.selected_session_id) == 2
        appended = index.canonical_session_rows(fixture.selected_session_id)
        assert first_ids < _entity_ids(appended)
        assert index.session_for_experiment("job-1", "sample-1") == (
            fixture.selected_session_id
        )
        assert index.experiment_for_session(fixture.selected_session_id) == (
            "job-1",
            "sample-1",
        )

    with IndexStore.recreate(source) as rebuilt:
        projector = SessionIndexProjector(registry, rebuilt)
        projector.rebuild(fixture.selected_session_id)
        recreated = rebuilt.canonical_session_rows(fixture.selected_session_id)

    assert _without_generation(appended) == _without_generation(recreated)


def test_rebuild_reads_only_selected_sources_and_never_mutates_them(
    tmp_path: Path,
) -> None:
    fixture = _rich_fixture(tmp_path, session_count=2)
    unrelated = fixture.config_dir / "profiles" / "alpha" / "sessions" / "session-001"
    (unrelated / "agent.jsonl").write_text("{invalid", encoding="utf-8")
    (unrelated / "gateway.db").write_bytes(b"not a sqlite database")
    retained = (
        fixture.config_dir / "registry.db",
        fixture.selected_session_dir / "agent.jsonl",
        fixture.selected_session_dir / "operator-messages.json",
        fixture.selected_session_dir / "gateway.db",
    )
    before = {source: source.read_bytes() for source in retained}

    with IndexStore(tmp_path / "index.sqlite3") as index:
        SessionIndexProjector(
            RegistryDatabase(fixture.config_dir),
            index,
        ).rebuild(fixture.selected_session_id)
        assert index.catalog_page(limit=5).entries[0].session_id == (
            fixture.selected_session_id
        )

    assert {source: source.read_bytes() for source in retained} == before


def test_wal_reader_observes_one_complete_generation_during_rebuild(
    tmp_path: Path,
) -> None:
    fixture = _rich_fixture(tmp_path)
    source = tmp_path / "index.sqlite3"
    with IndexStore(source) as index:
        projector = SessionIndexProjector(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        assert projector.rebuild(fixture.selected_session_id) == 1
        with sqlite3.connect(source) as reader:
            reader.execute("BEGIN")
            assert (
                reader.execute(
                    "SELECT generation FROM sessions WHERE session_id = ?",
                    (fixture.selected_session_id,),
                ).fetchone()[0]
                == 1
            )

            _append_agent_record(
                fixture.selected_session_dir,
                {
                    "phase": "reasoning",
                    "text": "Inspect the fountain",
                    "at": "2026-08-01T00:00:08+00:00",
                },
            )
            assert projector.rebuild(fixture.selected_session_id) == 2
            assert (
                reader.execute(
                    "SELECT generation FROM sessions WHERE session_id = ?",
                    (fixture.selected_session_id,),
                ).fetchone()[0]
                == 1
            )
            assert index.catalog_page(limit=1).entries[0].generation == 2


def test_goal_nudge_and_repeated_number_identity_uses_applied_boundaries(
    tmp_path: Path,
) -> None:
    fixture = _rich_fixture(tmp_path)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        SessionIndexProjector(
            RegistryDatabase(fixture.config_dir),
            index,
        ).rebuild(fixture.selected_session_id)
        rows = _rows(index.canonical_session_rows(fixture.selected_session_id))

    entities = {row["id"]: row for row in rows if row["table"] == "entities"}
    turns = [row for row in entities.values() if row["kind"] == "turn"]
    iterations = [row for row in entities.values() if row["kind"] == "iteration"]
    goals = [row for row in entities.values() if row["kind"] == "goal"]
    nudges = [row for row in entities.values() if row["kind"] == "nudge"]

    assert len({row["id"] for row in turns}) == 2
    assert len({row["id"] for row in iterations}) == 2
    assert len(goals) == 3
    assert len(nudges) == 2
    assert all("pending-goal" not in row["source_anchor"] for row in goals)

    goal_a = next(
        row for row in goals if row["source_anchor"] == "operator:goal-a:revise"
    )
    goal_b = next(
        row for row in goals if row["source_anchor"] == "operator:goal-b:revise"
    )
    nudge_a = next(
        row for row in nudges if row["source_anchor"] == "operator:nudge-a:guide"
    )
    nudge_b = next(
        row for row in nudges if row["source_anchor"] == "operator:nudge-b:guide"
    )
    assert nudge_a["parent_id"] == goal_a["id"]
    assert nudge_b["parent_id"] == goal_a["id"]
    assert nudge_b["parent_id"] != goal_b["id"]


def test_operator_control_record_owns_goal_revision_boundary(tmp_path: Path) -> None:
    fixture = _rich_fixture(tmp_path)
    identity = {
        "session_id": fixture.selected_session_id,
        "player_id": "alpha",
    }
    records = [
        {
            **identity,
            "phase": "session_start",
            "objective": {"title": "Initial goal"},
            "at": "2026-08-01T00:00:00+00:00",
        },
        {
            **identity,
            "phase": "turn",
            "n": 1,
            "at": "2026-08-01T00:00:01+00:00",
        },
        {
            **identity,
            "phase": "iteration",
            "n": 1,
            "at": "2026-08-01T00:00:02+00:00",
        },
        {
            **identity,
            "phase": "response",
            "text": "First goal response",
            "at": "2026-08-01T00:00:03+00:00",
        },
        {
            **identity,
            "phase": "turn",
            "n": 2,
            "at": "2026-08-01T00:00:04+00:00",
        },
        {
            **identity,
            "phase": "operator_control",
            "request_id": "goal-b",
            "action": "revise",
            "iteration": 0,
            "instruction": "Revised goal",
            "at": "2026-08-01T00:00:05+00:00",
        },
        {
            **identity,
            "phase": "iteration",
            "n": 1,
            "at": "2026-08-01T00:00:06+00:00",
        },
        {
            **identity,
            "phase": "response",
            "text": "Second goal response",
            "at": "2026-08-01T00:00:07+00:00",
        },
    ]
    (fixture.selected_session_dir / "agent.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    (fixture.selected_session_dir / "operator-messages.json").write_text(
        json.dumps(
            {
                "version": 1,
                "messages": [
                    _message("goal-b", "revise", "Revised goal", 0, 5),
                ],
            }
        ),
        encoding="utf-8",
    )

    with IndexStore(tmp_path / "index.sqlite3") as index:
        SessionIndexProjector(
            RegistryDatabase(fixture.config_dir),
            index,
        ).rebuild(fixture.selected_session_id)
        rows = _rows(index.canonical_session_rows(fixture.selected_session_id))

    entities = {row["source_anchor"]: row for row in rows if row["table"] == "entities"}
    initial_goal = entities["agent:1:initial"]["id"]
    revised_goal = entities["operator:goal-b:revise"]["id"]
    assert entities["agent:3"]["goal_id"] == initial_goal
    assert entities["agent:4"]["goal_id"] == initial_goal
    assert entities["agent:6"]["goal_id"] == revised_goal
    assert entities["agent:7"]["goal_id"] == revised_goal
    assert entities["agent:8"]["goal_id"] == revised_goal


def test_idle_first_goal_receipt_completes_stable_initial_goal(tmp_path: Path) -> None:
    fixture = _rich_fixture(tmp_path)
    identity = {
        "session_id": fixture.selected_session_id,
        "player_id": "alpha",
    }
    records = [
        {
            **identity,
            "phase": "session_start",
            "objective": {"title": "Find Fido"},
            "at": "2026-08-01T00:00:00+00:00",
        },
        {
            **identity,
            "phase": "turn",
            "n": 1,
            "at": "2026-08-01T00:00:01+00:00",
        },
        {
            **identity,
            "phase": "iteration",
            "n": 1,
            "at": "2026-08-01T00:00:02+00:00",
        },
    ]
    (fixture.selected_session_dir / "agent.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    (fixture.selected_session_dir / "operator-messages.json").write_text(
        json.dumps(
            {
                "version": 1,
                "messages": [
                    _message(
                        "initial-request",
                        "revise",
                        "Find Fido",
                        0,
                        1,
                    ),
                ],
            }
        ),
        encoding="utf-8",
    )

    with IndexStore(tmp_path / "index.sqlite3") as index:
        SessionIndexProjector(
            RegistryDatabase(fixture.config_dir),
            index,
        ).rebuild(fixture.selected_session_id)
        rows = _rows(index.canonical_session_rows(fixture.selected_session_id))

    entities = [row for row in rows if row["table"] == "entities"]
    goals = [row for row in entities if row["kind"] == "goal"]
    initial_goal = stable_entity_id(
        fixture.selected_session_id,
        "goal",
        "agent:1:initial",
    )
    assert [goal["id"] for goal in goals] == [initial_goal]
    assert next(row for row in entities if row["kind"] == "turn")["goal_id"] == (
        initial_goal
    )
    assert (
        next(row for row in entities if row["kind"] == "iteration")["goal_id"]
        == initial_goal
    )


def test_failed_rebuild_preserves_previous_generation_and_other_session(
    tmp_path: Path,
) -> None:
    fixture = _rich_fixture(tmp_path, session_count=2)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        projector = SessionIndexProjector(registry, index)
        projector.rebuild("session-001")
        projector.rebuild(fixture.selected_session_id)
        selected_before = index.canonical_session_rows(fixture.selected_session_id)
        other_before = index.canonical_session_rows("session-001")

        path = fixture.selected_session_dir / "operator-messages.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["messages"][0]["applied_at"] = None
        path.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(IndexBuildError):
            projector.rebuild(fixture.selected_session_id)

        assert index.canonical_session_rows(fixture.selected_session_id) == (
            selected_before
        )
        assert index.canonical_session_rows("session-001") == other_before


def test_catalog_is_keyset_bounded_and_uses_covering_index(tmp_path: Path) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=66)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        projector = SessionIndexProjector(registry, index)
        for session_number in range(12):
            projector.rebuild(f"session-{session_number:03d}")

        first = index.catalog_page(limit=5)
        assert len(first.entries) == 5
        assert first.next_cursor is not None
        second = index.catalog_page(limit=5, after=first.next_cursor)
        assert len(second.entries) == 5
        assert {entry.session_id for entry in first.entries}.isdisjoint(
            entry.session_id for entry in second.entries
        )
        plan = index.catalog_query_plan()
        assert any("sessions_catalog" in detail for detail in plan)
        assert all("COVERING INDEX" in detail for detail in plan)
        assert all("SEARCH sessions" in detail for detail in plan)
        assert all("COUNT" not in detail.upper() for detail in plan)

        cursor = CatalogCursor(updated_at="9999", session_id="zzzz")
        assert len(index.catalog_page(limit=5, after=cursor).entries) == 5


def test_search_is_deterministic_literal_and_secret_safe(tmp_path: Path) -> None:
    fixture = _rich_fixture(tmp_path)
    source = fixture.selected_session_dir / "agent.jsonl"
    records = [
        json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
    ]
    records[0]["objective"]["title"] = "Find Fido authorization=Bearer-secret"
    source.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    operator_source = fixture.selected_session_dir / "operator-messages.json"
    operator = json.loads(operator_source.read_text(encoding="utf-8"))
    operator["messages"].append(
        _message("secret-goal", "revise", "password=hunter2", 2, 6)
    )
    operator_source.write_text(json.dumps(operator), encoding="utf-8")
    _append_agent_record(
        fixture.selected_session_dir,
        {
            "phase": "reasoning",
            "text": (
                "Find Fido authorization=Bearer-secret "
                "sk-ant-example /Users/example/private "
                "0123456789abcdef0123456789abcdef"
            ),
            "at": "2026-08-01T00:00:08+00:00",
        },
    )
    _append_gateway(
        fixture.selected_session_dir,
        kind="wire_text",
        payload={
            "text": "hidden Fido password=secret",
            "redacted": True,
        },
        trace_id=None,
    )
    with IndexStore(tmp_path / "index.sqlite3") as index:
        projector = SessionIndexProjector(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        projector.rebuild(fixture.selected_session_id)
        first = index.search("Fido", session_id=fixture.selected_session_id)
        second = index.search("Fido", session_id=fixture.selected_session_id)
        malicious = index.search(
            'Fido OR "*"',
            session_id=fixture.selected_session_id,
        )
        dump = "\n".join(index.canonical_session_rows(fixture.selected_session_id))
        assert first == second
        assert malicious == ()
        assert first
        assert "Bearer-secret" not in dump
        assert "password=hunter2" not in dump
        assert "hunter2" not in dump
        assert "sk-ant-example" not in dump
        assert "/Users/example/private" not in dump
        assert "0123456789abcdef0123456789abcdef" not in dump
        assert all("hidden Fido" not in hit.body for hit in first)
        assert "[REDACTED]" in dump
        assert "[LOCAL_PATH]" in dump

        targets = tuple(hit.entity_id for hit in first)
        projector.rebuild(fixture.selected_session_id)
        assert (
            tuple(
                hit.entity_id
                for hit in index.search(
                    "Fido",
                    session_id=fixture.selected_session_id,
                )
            )
            == targets
        )


def test_missing_trace_stays_uncorrelated_and_native_trace_is_session_scoped(
    tmp_path: Path,
) -> None:
    fixture = _rich_fixture(tmp_path)
    _append_gateway(
        fixture.selected_session_dir,
        kind="command",
        payload={"line": "look"},
        trace_id=None,
    )
    with IndexStore(tmp_path / "index.sqlite3") as index:
        SessionIndexProjector(
            RegistryDatabase(fixture.config_dir),
            index,
        ).rebuild(fixture.selected_session_id)
        rows = _rows(index.canonical_session_rows(fixture.selected_session_id))

    traces = [row for row in rows if row.get("kind") == "trace"]
    gateway = [
        row
        for row in rows
        if row.get("source_anchor", "").startswith("gateway:")
        and row.get("kind") == "record"
    ]
    assert len(traces) == 1
    assert traces[0]["source_anchor"] == "gateway:gateway-000:trace:trace-1"
    assert any(
        row["parent_id"] is None or row["parent_id"] != traces[0]["id"]
        for row in gateway
    )


def _rich_fixture(root: Path, *, session_count: int = 3) -> RetainedFixture:
    fixture = build_retained_fixture(root, session_count=session_count)
    identity = {
        "session_id": fixture.selected_session_id,
        "player_id": "alpha",
    }
    records = [
        {
            **identity,
            "phase": "session_start",
            "objective": {"title": "Find Fido"},
            "at": "2026-08-01T00:00:00+00:00",
        },
        {
            **identity,
            "phase": "turn",
            "n": 1,
            "instruction": "Find Fido",
            "at": "2026-08-01T00:00:01+00:00",
        },
        {
            **identity,
            "phase": "iteration",
            "n": 1,
            "at": "2026-08-01T00:00:02+00:00",
        },
        {
            **identity,
            "phase": "response",
            "text": "I will inspect the park",
            "at": "2026-08-01T00:00:03+00:00",
        },
        {
            **identity,
            "phase": "turn",
            "n": 1,
            "attempt": 2,
            "instruction": "Retry",
            "at": "2026-08-01T00:00:04+00:00",
        },
        {
            **identity,
            "phase": "iteration",
            "n": 1,
            "at": "2026-08-01T00:00:05+00:00",
        },
    ]
    (fixture.selected_session_dir / "agent.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    messages = [
        _message("goal-a", "revise", "Search the park", 1, 1),
        _message("nudge-a", "guide", "Check the fountain", 1, 2),
        _message("nudge-b", "guide", "Ask the guard", 2, 3),
        _message("goal-b", "revise", "Find the bakery", 2, 4),
        _message("pending-goal", "revise", "Wait", None, 5),
    ]
    (fixture.selected_session_dir / "operator-messages.json").write_text(
        json.dumps({"version": 1, "messages": messages}, sort_keys=True),
        encoding="utf-8",
    )
    with sqlite3.connect(fixture.config_dir / "registry.db") as database:
        database.execute(
            """
            UPDATE sessions
            SET experiment_id = ?, run_id = ?
            WHERE session_id = ?
            """,
            ("job-1", "sample-1", fixture.selected_session_id),
        )
    return fixture


def _message(
    request_id: str,
    action: str,
    instruction: str,
    applied_iteration: int | None,
    order: int,
) -> dict[str, object]:
    return {
        "request_id": request_id,
        "action": action,
        "instruction": instruction,
        "sent_at": f"2026-08-01T00:00:{order:02d}+00:00",
        "applied_iteration": applied_iteration,
        "applied_at": (
            None if applied_iteration is None else f"2026-08-01T00:01:{order:02d}+00:00"
        ),
    }


def _append_agent_record(session_dir: Path, record: dict[str, object]) -> None:
    with (session_dir / "agent.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "session_id": "session-000",
                    "player_id": "alpha",
                    **record,
                }
            )
            + "\n"
        )


def _append_gateway(
    session_dir: Path,
    *,
    kind: str,
    payload: dict[str, object],
    trace_id: str | None,
) -> None:
    with sqlite3.connect(session_dir / "gateway.db") as database:
        database.execute(
            """
            INSERT INTO events (
                session, at, monotonic, kind, trace_id, payload
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "gateway-000",
                9.0,
                9.0,
                kind,
                trace_id,
                json.dumps(payload),
            ),
        )


def _rows(dump: tuple[str, ...]) -> list[dict[str, Any]]:
    return [json.loads(row) for row in dump]


def _entity_ids(dump: tuple[str, ...]) -> set[str]:
    return {str(row["id"]) for row in _rows(dump) if row["table"] == "entities"}


def _without_generation(dump: tuple[str, ...]) -> tuple[str, ...]:
    normalized = []
    for row in _rows(dump):
        if row["table"] == "sessions":
            row["generation"] = 1
        normalized.append(json.dumps(row, sort_keys=True, separators=(",", ":")))
    return tuple(normalized)
