"""Composite cursor, incremental advancement, and singleflight gates."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from observatory_v3_backend.app import create_app
from observatory_v3_backend.errors import MalformedSourceError
from observatory_v3_backend.index import IndexStore
from observatory_v3_backend.index.models import (
    SessionCheckpoint,
    SessionProjection,
    SourceWatermark,
)
from observatory_v3_backend.index.projector import IndexBuildError
from observatory_v3_backend.materialization import (
    MaterializerBusyError,
    SessionMaterializer,
)
from observatory_v3_backend.materialization.advance import (
    IncrementalSessionAdvancer,
)
from observatory_v3_backend.materialization.models import (
    AdvanceMetrics,
    MaterializationResult,
)
from observatory_v3_backend.models import AgentPage, SessionRecord
from observatory_v3_backend.repositories import (
    RegistryDatabase,
    SessionLookupRepository,
)
from observatory_v3_backend.repositories.agent import AgentRepository
from observatory_v3_backend.repositories.operator import OperatorRepository
from observatory_v3_backend.settings import Settings

from .fixtures import RetainedFixture, build_retained_fixture


def test_increment_reads_only_new_agent_and_gateway_suffix(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        first = advancer.advance(fixture.selected_session_id)
        checkpoint = _checkpoint(index, fixture)
        first_rows = _entity_rows(
            index.canonical_session_rows(fixture.selected_session_id)
        )

        _append_agent(
            fixture,
            phase="reasoning",
            text="Look behind the fountain",
            at="2026-08-01T00:00:03+00:00",
        )
        gateway_sequence = _append_gateway(fixture)
        second = advancer.advance(fixture.selected_session_id)
        committed = _checkpoint(index, fixture)

        assert first.kind == "bootstrap"
        assert second.kind == "incremental"
        assert second.metrics.agent_start_offset == (checkpoint.watermark.agent_offset)
        assert second.metrics.agent_records == 1
        assert second.metrics.gateway_after_sequence == (
            checkpoint.watermark.gateway_sequence
        )
        assert second.metrics.gateway_records == 1
        assert committed.watermark.gateway_sequence == gateway_sequence
        assert committed.watermark.agent_offset > checkpoint.watermark.agent_offset
        assert committed.generation == checkpoint.generation + 1
        assert first.cursor != second.cursor
        assert second.cursor.startswith("obc1_")
        assert committed.watermark.agent_source_id not in second.cursor
        assert committed.watermark.gateway_source_id not in second.cursor
        assert set(first_rows) < set(
            _entity_rows(index.canonical_session_rows(fixture.selected_session_id))
        )


def test_bootstrap_rejects_agent_replacement_during_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    original = AgentRepository.page
    replaced = False

    def replace_after_read(
        repository: AgentRepository,
        *,
        offset: int = 0,
        start_line: int = 1,
        limit: int = 250,
    ) -> AgentPage:
        nonlocal replaced
        page = original(
            repository,
            offset=offset,
            start_line=start_line,
            limit=limit,
        )
        if not replaced:
            replaced = True
            _replace_agent_source(fixture)
        return page

    monkeypatch.setattr(AgentRepository, "page", replace_after_read)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(registry, index)
        with pytest.raises(
            IndexBuildError,
            match="agent_source_changed_during_projection",
        ):
            advancer.advance(fixture.selected_session_id)
        assert index.checkpoint(fixture.selected_session_id) is None

        recovered = advancer.advance(fixture.selected_session_id)
        rows = "\n".join(index.canonical_session_rows(fixture.selected_session_id))
        assert recovered.kind == "bootstrap"
        assert "wait south" in rows
        assert "look north" not in rows


@pytest.mark.asyncio
async def test_terminal_bootstrap_catches_append_after_projection_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    _stop_session(fixture)
    registry = RegistryDatabase(fixture.config_dir)
    original_replace = IndexStore.replace_session
    appended = False

    def append_before_commit(
        index: IndexStore,
        projection: SessionProjection,
    ) -> int:
        nonlocal appended
        if not appended:
            appended = True
            _append_agent(
                fixture,
                phase="reasoning",
                text="Appended after bootstrap projection",
            )
        return original_replace(index, projection)

    monkeypatch.setattr(IndexStore, "replace_session", append_before_commit)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        materializer = SessionMaterializer(registry, index, workers=1)
        result = await materializer.materialize(fixture.selected_session_id)
        checkpoint = _checkpoint(index, fixture)
        await materializer.close()

        assert result.terminal
        assert result.metrics.agent_start_offset == 0
        assert result.metrics.agent_records == 3
        assert result.metrics.gateway_after_sequence == 0
        assert result.metrics.gateway_records == 2
        assert result.metrics.lifecycle_after_sequence == 0
        assert result.metrics.lifecycle_records == 1
        assert result.metrics.passes == 2
        assert (
            checkpoint.watermark.agent_offset
            == (fixture.selected_session_dir / "agent.jsonl").stat().st_size
        )


def test_recovery_preserves_prior_generation_on_agent_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    source = tmp_path / "index.sqlite3"
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(source) as index:
        advancer = IncrementalSessionAdvancer(registry, index)
        advancer.advance(fixture.selected_session_id)
        before_entities = _entity_rows(
            index.canonical_session_rows(fixture.selected_session_id)
        )
        with sqlite3.connect(source) as database:
            database.execute(
                """
                UPDATE source_watermarks
                SET gateway_source_id = 'unknown'
                WHERE session_id = ?
                """,
                (fixture.selected_session_id,),
            )
        before = _checkpoint(index, fixture)
        original = AgentRepository.page
        replaced = False

        def replace_after_read(
            repository: AgentRepository,
            *,
            offset: int = 0,
            start_line: int = 1,
            limit: int = 250,
        ) -> AgentPage:
            nonlocal replaced
            page = original(
                repository,
                offset=offset,
                start_line=start_line,
                limit=limit,
            )
            if not replaced:
                replaced = True
                _replace_agent_source(fixture)
            return page

        monkeypatch.setattr(AgentRepository, "page", replace_after_read)
        fault = advancer.advance(fixture.selected_session_id)
        faulted = _checkpoint(index, fixture)
        retained = "\n".join(index.canonical_session_rows(fixture.selected_session_id))
        assert fault.kind == "fault"
        assert fault.fault == "malformed_source"
        assert faulted.watermark == before.watermark
        assert faulted.generation == before.generation + 1
        assert (
            _entity_rows(index.canonical_session_rows(fixture.selected_session_id))
            == before_entities
        )
        assert "look north" in retained
        assert "wait south" not in retained

        recovered = advancer.advance(fixture.selected_session_id)
        rebuilt = "\n".join(index.canonical_session_rows(fixture.selected_session_id))
        assert recovered.kind == "recovered"
        assert recovered.metrics.agent_start_offset == 0
        assert recovered.metrics.agent_records == 2
        assert recovered.metrics.gateway_after_sequence == 0
        assert recovered.metrics.gateway_records == 2
        assert recovered.metrics.lifecycle_after_sequence == 0
        assert recovered.metrics.lifecycle_records == 1
        assert "wait south" in rebuilt
        assert "look north" not in rebuilt


@pytest.mark.asyncio
async def test_terminal_schema_recovery_catches_append_before_replace_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    source = tmp_path / "index.sqlite3"
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(source) as index:
        IncrementalSessionAdvancer(registry, index).advance(fixture.selected_session_id)
        with sqlite3.connect(source) as database:
            database.execute(
                """
                UPDATE source_watermarks
                SET gateway_source_id = 'unknown'
                WHERE session_id = ?
                """,
                (fixture.selected_session_id,),
            )
        _stop_session(fixture)
        original_replace = IndexStore.replace_session
        appended = False

        def append_before_commit(
            store: IndexStore,
            projection: SessionProjection,
        ) -> int:
            nonlocal appended
            if not appended:
                appended = True
                _append_agent(
                    fixture,
                    phase="reasoning",
                    text="Appended after recovery projection",
                )
            return original_replace(store, projection)

        monkeypatch.setattr(IndexStore, "replace_session", append_before_commit)
        materializer = SessionMaterializer(registry, index, workers=1)
        result = await materializer.materialize(fixture.selected_session_id)
        checkpoint = _checkpoint(index, fixture)
        await materializer.close()

        assert result.terminal
        assert result.metrics.agent_start_offset == 0
        assert result.metrics.agent_records == 3
        assert result.metrics.gateway_after_sequence == 0
        assert result.metrics.gateway_records == 2
        assert result.metrics.lifecycle_after_sequence == 0
        assert result.metrics.lifecycle_records == 1
        assert result.metrics.passes == 2
        assert (
            checkpoint.watermark.agent_offset
            == (fixture.selected_session_dir / "agent.jsonl").stat().st_size
        )


def test_partial_agent_tail_waits_for_newline_without_losing_offset(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        advancer.advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        source = fixture.selected_session_dir / "agent.jsonl"
        record = json.dumps(
            {
                "session_id": fixture.selected_session_id,
                "player_id": "alpha",
                "phase": "reasoning",
                "text": "Incomplete until framed",
            }
        )
        with source.open("a", encoding="utf-8") as handle:
            handle.write(record)

        partial = advancer.advance(fixture.selected_session_id)
        retained = _checkpoint(index, fixture)
        assert partial.kind == "incremental"
        assert retained.watermark.agent_offset == before.watermark.agent_offset
        assert "agent_incomplete_tail" in retained.capture_gaps

        with source.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        complete = advancer.advance(fixture.selected_session_id)
        finished = _checkpoint(index, fixture)
        assert complete.metrics.agent_records == 1
        assert finished.watermark.agent_offset > before.watermark.agent_offset
        assert "agent_incomplete_tail" not in finished.capture_gaps


def test_unchanged_operator_snapshot_is_not_reparsed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        advancer.advance(fixture.selected_session_id)
        _append_agent(fixture, phase="reasoning", text="New evidence")

        def fail_snapshot(_repository: OperatorRepository) -> object:
            raise AssertionError("unchanged operator snapshot was reparsed")

        monkeypatch.setattr(OperatorRepository, "snapshot", fail_snapshot)
        result = advancer.advance(fixture.selected_session_id)
        assert result.metrics.agent_records == 1


def test_atomic_operator_revision_adds_one_goal(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    source = fixture.selected_session_dir / "operator-messages.json"
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        advancer.advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["messages"].append(
            {
                "request_id": "goal-2",
                "action": "revise",
                "instruction": "Return to the market",
                "sent_at": "2026-08-01T00:02:00+00:00",
                "applied_iteration": 3,
                "applied_at": "2026-08-01T00:02:01+00:00",
            }
        )
        replacement = source.with_suffix(".next")
        replacement.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(replacement, source)

        result = advancer.advance(fixture.selected_session_id)
        after = _checkpoint(index, fixture)
        assert result.kind == "incremental"
        assert after.goal_count == before.goal_count + 1
        assert after.latest_goal == "Return to the market"
        assert after.watermark.operator_source_id != (
            before.watermark.operator_source_id
        )


def test_pending_operator_request_may_become_applied_once(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    source = fixture.selected_session_dir / "operator-messages.json"
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        advancer.advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["messages"].append(
            {
                "request_id": "goal-pending",
                "action": "revise",
                "instruction": "Return to the market",
                "sent_at": "2026-08-01T00:02:00+00:00",
                "applied_iteration": None,
                "applied_at": None,
            }
        )
        _replace_json(source, payload)

        pending = advancer.advance(fixture.selected_session_id)
        retained_pending = _checkpoint(index, fixture)
        assert pending.kind == "incremental"
        assert retained_pending.goal_count == before.goal_count

        payload["messages"][-1]["applied_iteration"] = 3
        payload["messages"][-1]["applied_at"] = "2026-08-01T00:02:01+00:00"
        _replace_json(source, payload)
        applied = advancer.advance(fixture.selected_session_id)
        retained_applied = _checkpoint(index, fixture)

        assert applied.kind == "incremental"
        assert retained_applied.goal_count == before.goal_count + 1
        assert retained_applied.latest_goal == "Return to the market"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("truncate", "operator_snapshot_truncated"),
        ("mutate", "operator_snapshot_history_changed"),
        ("boundary", "operator_application_boundary_changed"),
    ],
)
def test_operator_history_loss_preserves_committed_cursor_and_rows(
    tmp_path: Path,
    change: str,
    expected: str,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    source = fixture.selected_session_dir / "operator-messages.json"
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        advancer.advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        before_rows = index.canonical_session_rows(fixture.selected_session_id)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if change == "truncate":
            payload["messages"].pop()
        elif change == "boundary":
            payload["messages"][0]["applied_iteration"] = 999
            payload["messages"][0]["applied_at"] = "2099-01-01T00:00:00+00:00"
        else:
            payload["messages"][0]["instruction"] = "Changed history"
        replacement = source.with_suffix(".next")
        replacement.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(replacement, source)

        result = advancer.advance(fixture.selected_session_id)
        after = _checkpoint(index, fixture)

        assert result.kind == "fault"
        assert result.fault == expected
        assert after.watermark == before.watermark
        assert _entity_rows(
            index.canonical_session_rows(fixture.selected_session_id)
        ) == _entity_rows(before_rows)


@pytest.mark.parametrize("fault", ["replacement", "malformed"])
def test_agent_fault_preserves_committed_cursor_and_rows(
    tmp_path: Path,
    fault: str,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        advancer.advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        before_rows = index.canonical_session_rows(fixture.selected_session_id)
        source = fixture.selected_session_dir / "agent.jsonl"
        if fault == "replacement":
            replacement = source.with_suffix(".replacement")
            replacement.write_bytes(source.read_bytes())
            os.replace(replacement, source)
            expected = "agent_source_replaced"
        else:
            with source.open("a", encoding="utf-8") as handle:
                handle.write("{invalid}\n")
            expected = "malformed_source"

        result = advancer.advance(fixture.selected_session_id)
        after = _checkpoint(index, fixture)
        after_rows = index.canonical_session_rows(fixture.selected_session_id)

        assert result.kind == "fault"
        assert result.fault == expected
        assert after.watermark == before.watermark
        assert after.capture_status == "fault"
        assert expected in after.capture_gaps
        assert _entity_rows(after_rows) == _entity_rows(before_rows)


def test_atomic_agent_replacement_during_read_is_not_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        advancer.advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        before_rows = index.canonical_session_rows(fixture.selected_session_id)
        _append_agent(fixture, phase="reasoning", text="New evidence")
        original_page = AgentRepository.page

        def replace_after_read(
            repository: AgentRepository,
            *,
            offset: int = 0,
            start_line: int = 1,
            limit: int = 250,
        ) -> AgentPage:
            page = original_page(
                repository,
                offset=offset,
                start_line=start_line,
                limit=limit,
            )
            replacement = repository.source.with_suffix(".replacement")
            replacement.write_bytes(repository.source.read_bytes())
            os.replace(replacement, repository.source)
            return page

        monkeypatch.setattr(AgentRepository, "page", replace_after_read)
        result = advancer.advance(fixture.selected_session_id)
        after = _checkpoint(index, fixture)

        assert result.kind == "fault"
        assert result.fault == "agent_source_changed_during_read"
        assert after.watermark == before.watermark
        assert _entity_rows(
            index.canonical_session_rows(fixture.selected_session_id)
        ) == _entity_rows(before_rows)


def test_malformed_session_does_not_block_another_selected_session(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=2)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(registry, index)
        advancer.advance("session-000")
        advancer.advance("session-001")
        with (fixture.selected_session_dir / "agent.jsonl").open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write("{invalid}\n")
        assert advancer.advance("session-000").kind == "fault"
        assert advancer.advance("session-001").kind == "unchanged"


@pytest.mark.parametrize("source_kind", ["agent", "gateway"])
def test_source_truncation_is_a_capture_fault(
    tmp_path: Path,
    source_kind: str,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        advancer.advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        if source_kind == "agent":
            source = fixture.selected_session_dir / "agent.jsonl"
            source.write_bytes(source.read_bytes()[:20])
            expected = "agent_source_truncated"
        else:
            with sqlite3.connect(
                fixture.selected_session_dir / "gateway.db"
            ) as database:
                database.execute(
                    "DELETE FROM events WHERE session = ? AND seq = 2",
                    (fixture.selected_gateway_session_id,),
                )
            expected = "gateway_source_truncated"

        result = advancer.advance(fixture.selected_session_id)
        after = _checkpoint(index, fixture)
        assert result.kind == "fault"
        assert result.fault == expected
        assert after.watermark == before.watermark


def test_one_event_after_two_thousand_event_bootstrap_reads_one_event(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    with sqlite3.connect(fixture.selected_session_dir / "gateway.db") as database:
        database.executemany(
            """
            INSERT INTO events (
                session, at, monotonic, kind, trace_id, payload
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    fixture.selected_gateway_session_id,
                    float(sequence),
                    float(sequence),
                    "observation",
                    None,
                    '{"text":"bounded fixture"}',
                )
                for sequence in range(3, 2_001)
            ),
        )
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(
            RegistryDatabase(fixture.config_dir),
            index,
        )
        bootstrap = advancer.advance(fixture.selected_session_id)
        assert bootstrap.metrics.gateway_records == 2_000
        previous = _checkpoint(index, fixture).watermark.gateway_sequence
        appended = _append_gateway(fixture)

        result = advancer.advance(fixture.selected_session_id)
        assert result.metrics.gateway_after_sequence == previous
        assert result.metrics.gateway_records == 1
        assert _checkpoint(index, fixture).watermark.gateway_sequence == appended


@pytest.mark.asyncio
async def test_multiple_consumers_share_one_advancement_and_cancellation(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    fake = _BlockingAdvancer()
    with IndexStore(tmp_path / "index.sqlite3") as index:
        materializer = SessionMaterializer(
            RegistryDatabase(fixture.config_dir),
            index,
            workers=1,
            queue_capacity=1,
            advancer=fake,
        )
        first = asyncio.create_task(materializer.materialize("session-000"))
        await asyncio.to_thread(fake.started.wait, 1)
        consumers = [
            asyncio.create_task(materializer.materialize("session-000"))
            for _ in range(19)
        ]
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        fake.release.set()
        results = await asyncio.gather(*consumers)
        assert {result.session_id for result in results} == {"session-000"}
        assert fake.calls == 1
        await materializer.close()


@pytest.mark.asyncio
async def test_rapid_source_changes_coalesce_to_one_follow_up(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    fake = _BlockingAdvancer()
    with IndexStore(tmp_path / "index.sqlite3") as index:
        materializer = SessionMaterializer(
            RegistryDatabase(fixture.config_dir),
            index,
            workers=1,
            queue_capacity=1,
            advancer=fake,
        )
        active = asyncio.create_task(materializer.materialize("session-000"))
        await asyncio.to_thread(fake.started.wait, 1)
        for _ in range(20):
            await materializer.notify_source_changed("session-000")
        fake.release.set()
        await active
        assert fake.calls == 2
        await materializer.close()


@pytest.mark.asyncio
async def test_change_during_follow_up_is_preserved_for_successor(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    fake = _PhasedAdvancer(3)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        materializer = SessionMaterializer(
            RegistryDatabase(fixture.config_dir),
            index,
            workers=1,
            queue_capacity=1,
            advancer=fake,
        )
        first_consumer = asyncio.create_task(materializer.materialize("session-000"))
        await asyncio.to_thread(fake.started[0].wait, 1)
        await materializer.notify_source_changed("session-000")
        fake.release[0].set()

        await asyncio.to_thread(fake.started[1].wait, 1)
        await materializer.notify_source_changed("session-000")
        fake.release[1].set()
        await first_consumer

        await asyncio.to_thread(fake.started[2].wait, 1)
        successor_consumer = asyncio.create_task(
            materializer.materialize("session-000")
        )
        fake.release[2].set()
        await successor_consumer

        assert fake.calls == 3
        await materializer.close()


@pytest.mark.asyncio
async def test_materializer_workers_keep_the_event_loop_responsive(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    fake = _SlowAdvancer()
    delays: list[float] = []

    async def measure_loop() -> None:
        previous = asyncio.get_running_loop().time()
        for _ in range(50):
            await asyncio.sleep(0.001)
            current = asyncio.get_running_loop().time()
            delays.append(current - previous - 0.001)
            previous = current

    with IndexStore(tmp_path / "index.sqlite3") as index:
        materializer = SessionMaterializer(
            RegistryDatabase(fixture.config_dir),
            index,
            workers=4,
            queue_capacity=12,
            advancer=fake,
        )
        await asyncio.gather(
            measure_loop(),
            *(
                materializer.materialize(f"session-{number:03d}")
                for number in range(16)
            ),
        )
        await materializer.close()

    ordered = sorted(delays)
    p95 = ordered[max(0, int(len(ordered) * 0.95 + 0.999) - 1)]
    assert fake.peak == 4
    assert p95 < 0.025


@pytest.mark.asyncio
async def test_materializer_rejects_work_beyond_bounded_capacity(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    fake = _BlockingAdvancer()
    with IndexStore(tmp_path / "index.sqlite3") as index:
        materializer = SessionMaterializer(
            RegistryDatabase(fixture.config_dir),
            index,
            workers=1,
            queue_capacity=0,
            advancer=fake,
        )
        active = asyncio.create_task(materializer.materialize("session-000"))
        await asyncio.to_thread(fake.started.wait, 1)
        with pytest.raises(MaterializerBusyError):
            await materializer.materialize("session-001")
        fake.release.set()
        await active
        await materializer.close()


@pytest.mark.asyncio
async def test_application_lifespan_owns_and_releases_materializer(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path,
        )
    )
    async with application.router.lifespan_context(application):
        assert isinstance(
            application.state.session_materializer,
            SessionMaterializer,
        )
        assert isinstance(application.state.session_index, IndexStore)

    with IndexStore.for_runtime(fixture.config_dir):
        pass


def test_terminal_checkpoint_validates_coordinates_without_payload_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(registry, index)
        advancer.advance(fixture.selected_session_id)
        with sqlite3.connect(fixture.config_dir / "registry.db") as database:
            database.execute(
                """
                UPDATE sessions
                SET state = 'stopped',
                    updated_at = '2026-08-01T02:00:00+00:00',
                    ended_at = '2026-08-01T02:00:00+00:00'
                WHERE session_id = ?
                """,
                (fixture.selected_session_id,),
            )
        terminal = advancer.advance(fixture.selected_session_id)
        assert terminal.terminal

        def fail_read(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("terminal advancement read retained evidence")

        monkeypatch.setattr(
            "observatory_v3_backend.repositories.agent.AgentRepository.page",
            fail_read,
        )
        restarted = IncrementalSessionAdvancer(registry, index)
        assert restarted.advance(fixture.selected_session_id).kind == "unchanged"


def test_terminal_session_waits_for_incomplete_agent_tail(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    source = fixture.selected_session_dir / "agent.jsonl"
    with IndexStore(tmp_path / "index.sqlite3") as index:
        advancer = IncrementalSessionAdvancer(registry, index)
        advancer.advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        record = json.dumps(
            {
                "session_id": fixture.selected_session_id,
                "player_id": "alpha",
                "phase": "reasoning",
                "text": "Final retained thought",
            }
        )
        with source.open("a", encoding="utf-8") as handle:
            handle.write(record)
        with sqlite3.connect(fixture.config_dir / "registry.db") as database:
            database.execute(
                """
                UPDATE sessions
                SET state = 'stopped',
                    updated_at = '2026-08-01T02:00:00+00:00',
                    ended_at = '2026-08-01T02:00:00+00:00'
                WHERE session_id = ?
                """,
                (fixture.selected_session_id,),
            )

        partial = advancer.advance(fixture.selected_session_id)
        waiting = _checkpoint(index, fixture)
        assert not partial.terminal
        assert waiting.watermark.agent_offset == before.watermark.agent_offset
        assert "agent_incomplete_tail" in waiting.capture_gaps

        with source.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        completed = advancer.advance(fixture.selected_session_id)
        retained = _checkpoint(index, fixture)
        assert completed.terminal
        assert completed.metrics.agent_records == 1
        assert retained.watermark.agent_offset > before.watermark.agent_offset
        assert "agent_incomplete_tail" not in retained.capture_gaps


@pytest.mark.asyncio
async def test_terminal_transition_catches_up_before_becoming_immutable(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        IncrementalSessionAdvancer(registry, index).advance(fixture.selected_session_id)
        with sqlite3.connect(fixture.selected_session_dir / "gateway.db") as database:
            database.executemany(
                """
                INSERT INTO events (
                    session, at, monotonic, kind, trace_id, payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        fixture.selected_gateway_session_id,
                        float(sequence),
                        float(sequence),
                        "observation",
                        None,
                        '{"text":"late retained evidence"}',
                    )
                    for sequence in range(3, 2_004)
                ),
            )
            latest_gateway_sequence = database.execute(
                "SELECT MAX(seq) FROM events WHERE session = ?",
                (fixture.selected_gateway_session_id,),
            ).fetchone()[0]
            assert isinstance(latest_gateway_sequence, int)
        with sqlite3.connect(fixture.config_dir / "registry.db") as database:
            database.execute(
                """
                UPDATE sessions
                SET state = 'stopped',
                    updated_at = '2026-08-01T02:00:00+00:00',
                    ended_at = '2026-08-01T02:00:00+00:00'
                WHERE session_id = ?
                """,
                (fixture.selected_session_id,),
            )
        materializer = SessionMaterializer(registry, index, workers=1)
        result = await materializer.materialize(fixture.selected_session_id)
        checkpoint = _checkpoint(index, fixture)
        await materializer.close()

        assert result.terminal
        assert result.metrics.gateway_records == 2_001
        assert result.metrics.passes == 2
        assert checkpoint.state == "stopped"
        assert checkpoint.watermark.gateway_sequence == latest_gateway_sequence


@pytest.mark.asyncio
async def test_exact_gateway_page_preserves_incremental_result_kind(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        IncrementalSessionAdvancer(registry, index).advance(fixture.selected_session_id)
        before = _checkpoint(index, fixture)
        with sqlite3.connect(fixture.selected_session_dir / "gateway.db") as database:
            database.executemany(
                """
                INSERT INTO events (
                    session, at, monotonic, kind, trace_id, payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        fixture.selected_gateway_session_id,
                        float(sequence),
                        float(sequence),
                        "observation",
                        None,
                        '{"text":"page boundary evidence"}',
                    )
                    for sequence in range(3, 2_003)
                ),
            )
        materializer = SessionMaterializer(registry, index, workers=1)
        result = await materializer.materialize(fixture.selected_session_id)
        await materializer.close()

        assert result.kind == "incremental"
        assert result.metrics.gateway_records == 2_000
        assert result.metrics.passes == 2
        assert result.generation == before.generation + 1


@pytest.mark.asyncio
async def test_terminal_append_during_suffix_read_is_caught_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        IncrementalSessionAdvancer(registry, index).advance(fixture.selected_session_id)
        with sqlite3.connect(fixture.config_dir / "registry.db") as database:
            database.execute(
                """
                UPDATE sessions
                SET state = 'stopped',
                    updated_at = '2026-08-01T02:00:00+00:00',
                    ended_at = '2026-08-01T02:00:00+00:00'
                WHERE session_id = ?
                """,
                (fixture.selected_session_id,),
            )
        original_page = AgentRepository.page
        appended = False

        def append_after_read(
            repository: AgentRepository,
            *,
            offset: int = 0,
            start_line: int = 1,
            limit: int = 250,
        ) -> AgentPage:
            nonlocal appended
            page = original_page(
                repository,
                offset=offset,
                start_line=start_line,
                limit=limit,
            )
            if not appended:
                appended = True
                with repository.source.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "session_id": fixture.selected_session_id,
                                "player_id": "alpha",
                                "phase": "reasoning",
                                "text": "Appended during terminal read",
                            }
                        )
                        + "\n"
                    )
            return page

        monkeypatch.setattr(AgentRepository, "page", append_after_read)
        materializer = SessionMaterializer(registry, index, workers=1)
        result = await materializer.materialize(fixture.selected_session_id)
        checkpoint = _checkpoint(index, fixture)
        await materializer.close()

        assert result.terminal
        assert result.metrics.agent_records == 1
        assert result.metrics.passes == 2
        assert (
            checkpoint.watermark.agent_offset
            == (fixture.selected_session_dir / "agent.jsonl").stat().st_size
        )


@pytest.mark.asyncio
async def test_terminal_append_after_coordinate_validation_is_caught_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        IncrementalSessionAdvancer(registry, index).advance(fixture.selected_session_id)
        _stop_session(fixture)
        original = IncrementalSessionAdvancer._coordinates_current
        appended = False

        def append_after_validation(
            advancer: IncrementalSessionAdvancer,
            session: SessionRecord,
            watermark: SourceWatermark,
        ) -> bool:
            nonlocal appended
            current = original(advancer, session, watermark)
            if current and not appended:
                appended = True
                _append_agent(
                    fixture,
                    phase="reasoning",
                    text="Appended after coordinate validation",
                )
            return current

        monkeypatch.setattr(
            IncrementalSessionAdvancer,
            "_coordinates_current",
            append_after_validation,
        )
        materializer = SessionMaterializer(registry, index, workers=1)
        result = await materializer.materialize(fixture.selected_session_id)
        checkpoint = _checkpoint(index, fixture)
        await materializer.close()

        assert result.terminal
        assert result.metrics.agent_records == 1
        assert result.metrics.passes == 2
        assert (
            checkpoint.watermark.agent_offset
            == (fixture.selected_session_dir / "agent.jsonl").stat().st_size
        )


@pytest.mark.asyncio
async def test_running_append_during_coordinate_validation_is_caught_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        IncrementalSessionAdvancer(registry, index).advance(fixture.selected_session_id)
        original = IncrementalSessionAdvancer._coordinates_current
        appended = False

        def append_before_validation(
            advancer: IncrementalSessionAdvancer,
            session: SessionRecord,
            watermark: SourceWatermark,
        ) -> bool:
            nonlocal appended
            if not appended:
                appended = True
                _append_agent(
                    fixture,
                    phase="reasoning",
                    text="Appended during running coordinate validation",
                )
            return original(advancer, session, watermark)

        monkeypatch.setattr(
            IncrementalSessionAdvancer,
            "_coordinates_current",
            append_before_validation,
        )
        materializer = SessionMaterializer(registry, index, workers=1)
        result = await materializer.materialize(fixture.selected_session_id)
        checkpoint = _checkpoint(index, fixture)
        await materializer.close()

        assert not result.terminal
        assert result.metrics.agent_records == 1
        assert result.metrics.passes == 2
        assert (
            checkpoint.watermark.agent_offset
            == (fixture.selected_session_dir / "agent.jsonl").stat().st_size
        )


@pytest.mark.asyncio
async def test_terminal_change_notification_forces_follow_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    registry = RegistryDatabase(fixture.config_dir)
    with IndexStore(tmp_path / "index.sqlite3") as index:
        IncrementalSessionAdvancer(registry, index).advance(fixture.selected_session_id)
        _stop_session(fixture)
        original = IncrementalSessionAdvancer._coordinates_current
        final_validation = threading.Event()
        release = threading.Event()
        validation_calls = 0

        def block_after_final_validation(
            advancer: IncrementalSessionAdvancer,
            session: SessionRecord,
            watermark: SourceWatermark,
        ) -> bool:
            nonlocal validation_calls
            current = original(advancer, session, watermark)
            validation_calls += 1
            if validation_calls == 2 and current:
                _append_agent(
                    fixture,
                    phase="reasoning",
                    text="Appended before a terminal result",
                )
                final_validation.set()
                if not release.wait(timeout=2):
                    raise TimeoutError("terminal validation was not released")
            return current

        monkeypatch.setattr(
            IncrementalSessionAdvancer,
            "_coordinates_current",
            block_after_final_validation,
        )
        materializer = SessionMaterializer(registry, index, workers=1)
        active = asyncio.create_task(
            materializer.materialize(fixture.selected_session_id)
        )
        assert await asyncio.to_thread(final_validation.wait, 1)
        await materializer.notify_source_changed(fixture.selected_session_id)
        release.set()
        result = await active
        checkpoint = _checkpoint(index, fixture)
        await materializer.close()

        assert result.terminal
        assert result.metrics.agent_records == 1
        assert validation_calls >= 3
        assert (
            checkpoint.watermark.agent_offset
            == (fixture.selected_session_dir / "agent.jsonl").stat().st_size
        )


def test_operator_snapshot_rejects_oversized_file(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path)
    source = fixture.selected_session_dir / "operator-messages.json"
    source.write_bytes(b" " * (4 * 1024 * 1024 + 1))

    registry = RegistryDatabase(fixture.config_dir)
    session = SessionLookupRepository(registry).get(fixture.selected_session_id)
    assert session is not None
    with pytest.raises(MalformedSourceError, match="exceeds 4 MiB"):
        OperatorRepository(session).snapshot()


def _checkpoint(
    index: IndexStore,
    fixture: RetainedFixture,
) -> SessionCheckpoint:
    checkpoint = index.checkpoint(fixture.selected_session_id)
    assert checkpoint is not None
    return checkpoint


def _append_agent(
    fixture: RetainedFixture,
    **record: object,
) -> None:
    with (fixture.selected_session_dir / "agent.jsonl").open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(
                {
                    "session_id": fixture.selected_session_id,
                    "player_id": "alpha",
                    **record,
                }
            )
            + "\n"
        )


def _stop_session(fixture: RetainedFixture) -> None:
    with sqlite3.connect(fixture.config_dir / "registry.db") as database:
        database.execute(
            """
            UPDATE sessions
            SET state = 'stopped',
                updated_at = '2026-08-01T02:00:00+00:00',
                ended_at = '2026-08-01T02:00:00+00:00'
            WHERE session_id = ?
            """,
            (fixture.selected_session_id,),
        )


def _append_gateway(fixture: RetainedFixture) -> int:
    with sqlite3.connect(fixture.selected_session_dir / "gateway.db") as database:
        cursor = database.execute(
            """
            INSERT INTO events (
                session, at, monotonic, kind, trace_id, payload
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fixture.selected_gateway_session_id,
                4.0,
                4.0,
                "command",
                "trace-2",
                '{"line":"north"}',
            ),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def _replace_json(source: Path, payload: object) -> None:
    replacement = source.with_suffix(".next")
    replacement.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(replacement, source)


def _replace_agent_source(fixture: RetainedFixture) -> None:
    source = fixture.selected_session_dir / "agent.jsonl"
    replacement = source.with_suffix(".next")
    replacement.write_text(
        source.read_text(encoding="utf-8").replace("look north", "wait south"),
        encoding="utf-8",
    )
    os.replace(replacement, source)


def _entity_rows(rows: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(row for row in rows if '"table":"entities"' in row)


def _result(session_id: str, *, terminal: bool = False) -> MaterializationResult:
    return MaterializationResult(
        session_id=session_id,
        cursor=f"obc1_{session_id}",
        generation=1,
        kind="incremental",
        terminal=terminal,
        more_available=False,
        fault=None,
        metrics=AdvanceMetrics(
            agent_start_offset=0,
            agent_records=1,
            gateway_after_sequence=0,
            gateway_records=1,
            lifecycle_after_sequence=0,
            lifecycle_records=1,
        ),
    )


class _BlockingAdvancer:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def advance(self, session_id: str) -> MaterializationResult:
        self.calls += 1
        self.started.set()
        if not self.release.wait(timeout=2):
            raise TimeoutError("test advancement was not released")
        time.sleep(0.01)
        return _result(session_id)


class _SlowAdvancer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def advance(self, session_id: str) -> MaterializationResult:
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
        time.sleep(0.04)
        with self._lock:
            self._active -= 1
        return _result(session_id)


class _PhasedAdvancer:
    def __init__(self, phases: int) -> None:
        self.started = tuple(threading.Event() for _ in range(phases))
        self.release = tuple(threading.Event() for _ in range(phases))
        self.calls = 0

    def advance(self, session_id: str) -> MaterializationResult:
        index = self.calls
        self.calls += 1
        self.started[index].set()
        if not self.release[index].wait(timeout=2):
            raise TimeoutError("test advancement was not released")
        return _result(session_id)
