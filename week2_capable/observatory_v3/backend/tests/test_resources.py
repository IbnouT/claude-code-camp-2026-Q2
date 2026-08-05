"""Bounded resource behavior, drill-down, and performance gates."""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import time
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from statistics import median
from types import TracebackType
from typing import Any

import httpx
from mud_gateway.knowledge_schema import SCHEMA as KNOWLEDGE_SCHEMA

from observatory_v3_backend.app import create_app
from observatory_v3_backend.index.identity import stable_entity_id
from observatory_v3_backend.settings import Settings

from .fixtures import RetainedFixture, build_retained_fixture
from .readiness.fixture import build_readiness_fixture


async def test_catalog_uses_stable_keysets_and_fixed_page_limits(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=66)
    async with _client(fixture, tmp_path) as client:
        first = await client.get("/api/v1/sessions?limit=50")
        assert first.status_code == 200
        first_value = first.json()
        assert len(first_value["sessions"]) == 50
        assert first_value["continuation_cursor"].startswith("orc1_")

        second = await client.get(
            "/api/v1/sessions",
            params={"limit": 50, "cursor": first_value["continuation_cursor"]},
        )
        assert second.status_code == 200
        second_value = second.json()
        assert len(second_value["sessions"]) == 16
        assert second_value["continuation_cursor"] is None

        first_ids = {item["id"] for item in first_value["sessions"]}
        second_ids = {item["id"] for item in second_value["sessions"]}
        assert first_ids.isdisjoint(second_ids)

        malformed = await client.get(
            "/api/v1/sessions",
            params={"cursor": "orc1_not-valid"},
        )
        oversized = await client.get("/api/v1/sessions?limit=51")
    assert malformed.status_code == 422
    assert malformed.json()["error"] == "invalid_request"
    assert oversized.status_code == 422


async def test_session_progressive_drill_down_preserves_retained_forms(
    tmp_path: Path,
) -> None:
    fixture, wire_digest = _resource_fixture(tmp_path)
    session_id = fixture.selected_session_id
    async with _client(fixture, tmp_path) as client:
        summary = await _await_ready(client, f"/api/v1/sessions/{session_id}")
        goals = await client.get(f"/api/v1/sessions/{session_id}/goals")
        search = await client.get(
            f"/api/v1/sessions/{session_id}/search",
            params={"q": "structured city street"},
        )
        map_prefix = await client.get(f"/api/v1/sessions/{session_id}/map")
        cost = await client.get(f"/api/v1/sessions/{session_id}/cost")
        live = await client.get(f"/api/v1/live/{session_id}/thought-activity")
        wire = await client.get(
            f"/api/v1/sessions/{session_id}/wire/{wire_digest}",
            params={"max_bytes": 32},
        )

        assert summary.status_code == 200
        assert summary.json()["totals"] == {
            "goals": 2,
            "nudges": 1,
            "turns": 1,
            "iterations": 1,
            "records": 9,
            "tokens": 321,
            "cost_usd": 0.0123,
            "duration_ms": 420.0,
        }
        assert len(goals.json()["items"]) == 2
        assert search.json()["matches"]
        assert map_prefix.json()["current_room_id"] == "place:57"
        assert cost.json()["contributors"][0]["tokens"] == 321
        assert live.json()["stable_node_ids"]
        assert len(live.content) < 128 * 1024
        assert wire.status_code == 200
        assert wire.json()["digest"] == wire_digest
        assert wire.json()["truncated"] is True
        assert len(wire.json()["body"].encode()) <= 32

        index_source = fixture.config_dir / "observatory" / "index-v1.sqlite3"
        with sqlite3.connect(index_source) as database:
            rows = database.execute(
                """
                SELECT entity_id, evidence_kind
                FROM evidence_payloads
                WHERE session_id = ?
                ORDER BY evidence_kind
                """,
                (session_id,),
            ).fetchall()
        evidence = {}
        for record_id, evidence_kind in rows:
            response = await client.get(
                f"/api/v1/sessions/{session_id}/evidence/{record_id}"
            )
            assert response.status_code == 200
            value = response.json()
            assert value["integrity_digest"]
            assert value["source_refs"]
            evidence[str(evidence_kind)] = value["fields"]

    assert {
        "agent:model_input",
        "agent:reasoning",
        "agent:response",
        "gateway:parser_input",
        "gateway:observation",
        "gateway:wire_text",
    } <= set(evidence)
    assert evidence["gateway:parser_input"]["payload"]["text"] == "raw mud text"
    assert evidence["gateway:observation"]["payload"]["text"] == (
        "structured city street"
    )
    assert evidence["agent:model_input"]["model_visible_input"] == (
        "structured city street"
    )
    assert evidence["agent:reasoning"]["text"] == "Check the north gate"
    assert evidence["agent:response"]["text"] == "I found the route"


async def test_trace_children_errors_and_payload_budgets(tmp_path: Path) -> None:
    fixture, _digest = _resource_fixture(tmp_path)
    session_id = fixture.selected_session_id
    invalid_body = b"\xff" * 32
    invalid_digest = sha256(invalid_body).hexdigest()
    with sqlite3.connect(fixture.selected_session_dir / "gateway.db") as database:
        database.execute(
            "INSERT INTO blobs (digest, body) VALUES (?, ?)",
            (invalid_digest, invalid_body),
        )
    async with _client(fixture, tmp_path) as client:
        await client.get(f"/api/v1/sessions/{session_id}")
        trace = await client.get(
            f"/api/v1/sessions/{session_id}/traces/trace-1?limit=2"
        )
        missing = await client.get(f"/api/v1/sessions/{session_id}/evidence/unknown")
        wrong_cursor = await client.get(
            f"/api/v1/sessions/{session_id}/goals",
            params={"cursor": "orc1_not-valid"},
        )
        too_large_wire = await client.get(
            f"/api/v1/sessions/{session_id}/wire/{'0' * 64}",
            params={"max_bytes": 65_537},
        )
        bounded_wire = await client.get(
            f"/api/v1/sessions/{session_id}/wire/{invalid_digest}",
            params={"max_bytes": 8},
        )
    assert trace.status_code == 200
    assert len(trace.json()["items"]) == 2
    assert len(trace.content) < 256 * 1024
    assert missing.status_code == 404
    assert wrong_cursor.status_code == 422
    assert too_large_wire.status_code == 422
    assert bounded_wire.status_code == 200
    assert len(bounded_wire.json()["body"].encode()) <= 8
    assert bounded_wire.json()["byte_length"] <= 8
    assert bounded_wire.json()["truncated"] is True


async def test_warm_resource_latency_and_payload_budgets(
    tmp_path: Path,
    record_testsuite_property: Callable[[str, object], None],
) -> None:
    fixture, _digest = _resource_fixture(tmp_path)
    session_id = fixture.selected_session_id
    async with _client(fixture, tmp_path) as client:
        await client.get(f"/api/v1/sessions/{session_id}")
        timings: dict[str, list[float]] = {
            "summary": [],
            "goals": [],
            "live": [],
        }
        responses: dict[str, httpx.Response] = {}
        paths = {
            "summary": f"/api/v1/sessions/{session_id}",
            "goals": f"/api/v1/sessions/{session_id}/goals",
            "live": f"/api/v1/live/{session_id}/identity-lifecycle",
        }
        for name, path in paths.items():
            await client.get(path)
            for _sample in range(20):
                started = time.perf_counter()
                response = await client.get(path)
                timings[name].append((time.perf_counter() - started) * 1_000)
                responses[name] = response

    record_testsuite_property(
        "warm_resource_latency_ms",
        json.dumps(
            {
                name: {
                    "median": median(samples),
                    "p95": _nearest_rank_p95(samples),
                }
                for name, samples in timings.items()
            },
            sort_keys=True,
        ),
    )
    assert len(responses["summary"].content) < 64 * 1024
    assert len(responses["goals"].content) < 256 * 1024
    assert len(responses["live"].content) < 128 * 1024


async def test_experiment_and_knowledge_resources_are_bounded(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=3)
    _link_experiment_samples(fixture)
    _write_knowledge(fixture.config_dir)
    knowledge_source = fixture.config_dir / "profiles" / "alpha" / "knowledge.db"
    with sqlite3.connect(knowledge_source) as database:
        database.execute(
            """
            INSERT INTO snapshots (
                snapshot_id, cdc_high_water, reason, digest, generation, at
            ) VALUES ('snapshot-0', 2, 'test', ?, 1, 3.0)
            """,
            ("1" * 64,),
        )
        database.execute(
            """
            INSERT INTO knowledge_resets (
                reset_id, snapshot_id, reason, assertions, transaction_id, at
            ) VALUES ('reset-0', 'snapshot-0', 'test', 2, 'tx-reset', 4.0)
            """
        )
        database.execute(
            """
            INSERT INTO restores (
                restore_id, snapshot_id, reason, assertions, transaction_id, at
            ) VALUES ('restore-0', 'snapshot-0', 'test', 2, 'tx-restore', 5.0)
            """
        )
        database.executemany(
            """
            INSERT INTO evidence_refs (
                assertion_id, session_id, source_seq, wire_digest,
                parser_version, method, observed_at
            ) VALUES ('assertion-0', 'session-000', ?, ?, 'v1', 'parser', ?)
            """,
            ((sequence, "0" * 64, float(sequence)) for sequence in range(10, 50)),
        )
    async with _client(fixture, tmp_path) as client:
        for session_id in ("session-000", "session-001"):
            response = await _await_ready(
                client,
                f"/api/v1/sessions/{session_id}",
            )
            assert response.status_code == 200
            assert (
                await client.get(f"/api/v1/sessions/{session_id}/goals")
            ).status_code == 200
        catalog = await client.get("/api/v1/experiments?limit=1")
        detail = await client.get("/api/v1/experiments/experiment-a?limit=1")
        knowledge = await client.get("/api/v1/knowledge/alpha")
        assertions = await client.get("/api/v1/knowledge/alpha/assertion?limit=1")
        changes = await client.get("/api/v1/knowledge/alpha/change?limit=1")
        snapshots = await client.get("/api/v1/knowledge/alpha/snapshot?limit=1")
        recovery = await client.get("/api/v1/knowledge/alpha/recovery?limit=2")
        evidence_page = await client.get(
            "/api/v1/knowledge/alpha/assertions/assertion-0/evidence",
            params={"limit": 20},
        )
        evidence_next = await client.get(
            "/api/v1/knowledge/alpha/assertions/assertion-0/evidence",
            params={
                "limit": 100,
                "cursor": evidence_page.json()["continuation_cursor"],
            },
        )

    assert catalog.status_code == 200
    assert catalog.json()["experiments"][0]["sample_count"] == 2
    assert detail.status_code == 200
    assert len(detail.json()["samples"]) == 1
    assert detail.json()["continuation_cursor"].startswith("orc1_")
    assert knowledge.status_code == 200
    metrics = {item["id"]: item["value"] for item in knowledge.json()["metrics"]}
    assert metrics["current-facts"] == 2
    assert metrics["source-sessions"] == 1
    assert assertions.status_code == 200
    assert len(assertions.json()["items"]) == 1
    assert assertions.json()["continuation_cursor"].startswith("orc1_")
    assert assertions.json()["items"][0]["evidence_continuation_cursor"].startswith(
        "orc1_"
    )
    assert changes.status_code == 200
    assert changes.json()["items"][0]["kind"] == "change"
    assert snapshots.status_code == 200
    assert snapshots.json()["items"][0]["kind"] == "snapshot"
    assert recovery.status_code == 200
    assert {item["values"]["operation"] for item in recovery.json()["items"]} == {
        "reset",
        "restore",
    }
    assert len(evidence_page.json()["items"]) == 20
    assert len(evidence_next.json()["items"]) == 21


async def test_missing_retained_sources_are_explicit_capture_gaps(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=2)
    session_dir = fixture.config_dir / "profiles" / "alpha" / "sessions" / "session-001"
    async with _client(fixture, tmp_path) as client:
        response = await _await_ready(client, "/api/v1/sessions/session-001")

    assert response.status_code == 200
    assert response.json()["completeness"] == "partial"
    assert {
        "agent_log_unavailable",
        "gateway_journal_unavailable",
        "operator_messages_unavailable",
    } <= set(response.json()["capture_gaps"])
    assert not (session_dir / "agent.jsonl").exists()


async def test_session_summary_reads_the_latest_bounded_lifecycle_suffix(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=2)
    with sqlite3.connect(fixture.config_dir / "registry.db") as database:
        database.executemany(
            """
            INSERT INTO lifecycle (session_id, at, state, detail)
            VALUES (?, ?, ?, ?)
            """,
            (
                (
                    fixture.selected_session_id,
                    f"2026-08-01T00:{index:02d}:00+00:00",
                    f"state-{index}",
                    json.dumps({"index": index}),
                )
                for index in range(40)
            ),
        )
    async with _client(fixture, tmp_path) as client:
        response = await _await_ready(
            client,
            f"/api/v1/sessions/{fixture.selected_session_id}",
        )

    value = response.json()
    assert response.status_code == 200
    assert len(value["lifecycle"]) == 32
    assert value["lifecycle"][-1]["state"] == "state-39"
    assert "lifecycle_summary_truncated" in value["capture_gaps"]

    cursor = value["lifecycle_cursor"]
    retained = [item["sequence"] for item in value["lifecycle"]]
    async with _client(fixture, tmp_path) as client:
        while cursor is not None:
            page = await client.get(
                f"/api/v1/sessions/{fixture.selected_session_id}/lifecycle",
                params={"limit": 10, "cursor": cursor},
            )
            assert page.status_code == 200
            retained.extend(item["sequence"] for item in page.json()["items"])
            cursor = page.json()["continuation_cursor"]
    assert len(retained) == 41
    assert len(set(retained)) == 41


async def test_live_long_session_is_current_bounded_and_independently_versioned(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=3)
    gateway_source = fixture.selected_session_dir / "gateway.db"
    with sqlite3.connect(gateway_source) as database:
        database.execute("DELETE FROM events")
        database.executemany(
            """
            INSERT INTO events (
                session, at, monotonic, kind, trace_id, payload
            ) VALUES (?, ?, ?, 'observation', NULL, ?)
            """,
            (
                (
                    fixture.selected_gateway_session_id,
                    float(sequence),
                    float(sequence),
                    json.dumps(
                        {
                            "place_id": f"place:{sequence}",
                            "title": f"Place {sequence}",
                            "direction": "north",
                        }
                    ),
                )
                for sequence in range(1, 2_501)
            ),
        )
        database.execute(
            """
            INSERT INTO events (
                session, at, monotonic, kind, trace_id, payload
            ) VALUES (?, 2501, 2501, 'observation', NULL, ?)
            """,
            (
                fixture.selected_gateway_session_id,
                json.dumps(
                    {
                        "place_id": "place:1",
                        "title": "Revisited",
                        "direction": "west",
                    }
                ),
            ),
        )

    async with _client(fixture, tmp_path) as client:
        initial = await client.get(
            f"/api/v1/live/{fixture.selected_session_id}/world-map"
        )
        assert initial.status_code == 200
        initial_value = initial.json()
        assert initial_value["values"]["current_room_id"] == "place:1"
        assert len(initial_value["values"]["nodes"]) == 200
        assert "place:1" in {node["id"] for node in initial_value["values"]["nodes"]}
        assert len(initial.content) < 128 * 1024
        assert initial_value["completeness"] == "partial"
        assert "map_prefix_truncated" in initial_value["capture_gaps"]

        with sqlite3.connect(fixture.config_dir / "registry.db") as database:
            database.execute(
                """
                INSERT INTO lifecycle (session_id, at, state, detail)
                VALUES (?, '2026-08-01T02:00:00+00:00', 'observing', '{}')
                """,
                (fixture.selected_session_id,),
            )
        lifecycle_only = await client.get(
            f"/api/v1/live/{fixture.selected_session_id}/world-map"
        )
        assert lifecycle_only.json()["values"] == initial_value["values"]
        assert (
            lifecycle_only.json()["resource_version"]
            == (initial_value["resource_version"])
        )
        assert lifecycle_only.json()["source_cursor"] == initial_value["source_cursor"]

        # The Live partition omits transport pagination, so traverse the map resource.
        map_page = await client.get(
            f"/api/v1/sessions/{fixture.selected_session_id}/map"
        )
        cursor = map_page.json()["continuation_cursor"]
        retained_rooms = {node["id"] for node in map_page.json()["nodes"]}
        while cursor is not None:
            map_page = await client.get(
                f"/api/v1/sessions/{fixture.selected_session_id}/map",
                params={"cursor": cursor},
            )
            assert map_page.status_code == 200
            retained_rooms.update(node["id"] for node in map_page.json()["nodes"])
            cursor = map_page.json()["continuation_cursor"]
        assert retained_rooms == {f"place:{sequence}" for sequence in range(1, 2_501)}

        with sqlite3.connect(gateway_source) as database:
            database.execute(
                """
                INSERT INTO events (
                    session, at, monotonic, kind, trace_id, payload
                ) VALUES (?, 2502, 2502, 'observation', NULL, ?)
                """,
                (
                    fixture.selected_gateway_session_id,
                    json.dumps(
                        {
                            "place_id": "place:latest",
                            "title": "Latest",
                            "direction": "east",
                        }
                    ),
                ),
            )
        changed = await client.get(
            f"/api/v1/live/{fixture.selected_session_id}/world-map"
        )
    assert changed.json()["values"]["current_room_id"] == "place:latest"
    assert changed.json()["resource_version"] != initial_value["resource_version"]
    assert changed.json()["source_cursor"] != initial_value["source_cursor"]


async def test_goal_embedded_child_cursor_has_no_continuation_hole(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=3)
    messages = [
        {
            "request_id": "goal-many",
            "action": "revise",
            "instruction": "Inspect every route",
            "sent_at": "2026-08-01T00:00:00+00:00",
            "applied_iteration": 1,
            "applied_at": "2026-08-01T00:00:01+00:00",
        }
    ]
    messages.extend(
        {
            "request_id": f"nudge-{index}",
            "action": "guide",
            "instruction": f"Check route {index}",
            "sent_at": f"2026-08-01T00:{index + 1:02d}:00+00:00",
            "applied_iteration": index + 2,
            "applied_at": f"2026-08-01T00:{index + 1:02d}:01+00:00",
        }
        for index in range(12)
    )
    (fixture.selected_session_dir / "operator-messages.json").write_text(
        json.dumps({"version": 1, "messages": messages}, sort_keys=True),
        encoding="utf-8",
    )
    async with _client(fixture, tmp_path) as client:
        await _await_ready(
            client,
            f"/api/v1/sessions/{fixture.selected_session_id}",
        )
        goals = await client.get(
            f"/api/v1/sessions/{fixture.selected_session_id}/goals"
        )
        assert goals.status_code == 200
        goal = next(
            item
            for item in goals.json()["items"]
            if item["child_continuation_cursor"] is not None
        )
        retained = {item["id"] for item in (*goal["nudges"], *goal["turns"])}
        cursor = goal["child_continuation_cursor"]
        while cursor is not None:
            children = await client.get(
                (
                    f"/api/v1/sessions/{fixture.selected_session_id}"
                    f"/evidence/{goal['goal']['id']}/children"
                ),
                params={"cursor": cursor, "limit": 5},
            )
            assert children.status_code == 200
            retained.update(item["id"] for item in children.json()["items"])
            cursor = children.json()["continuation_cursor"]

        index_source = fixture.config_dir / "observatory" / "index-v1.sqlite3"
        with sqlite3.connect(index_source) as database:
            expected = {
                str(row[0])
                for row in database.execute(
                    """
                    SELECT id FROM entities
                    WHERE session_id = ? AND parent_id = ?
                    ORDER BY ordinal, id
                    """,
                    (fixture.selected_session_id, goal["goal"]["id"]),
                )
            }
    assert retained == expected
    assert len(retained) == 12


async def test_unsupported_cold_source_surfaces_sticky_capture_fault(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=3)
    with sqlite3.connect(fixture.selected_session_dir / "gateway.db") as database:
        database.execute("PRAGMA user_version=999")
    async with _client(fixture, tmp_path) as client:
        first = await client.get(f"/api/v1/sessions/{fixture.selected_session_id}")
        assert first.status_code == 202
        fault = await _await_terminal_response(
            client,
            f"/api/v1/sessions/{fixture.selected_session_id}",
        )
        repeated = await client.get(f"/api/v1/sessions/{fixture.selected_session_id}")
        catalog = await client.get("/api/v1/sessions")
    async with _client(fixture, tmp_path) as restarted_client:
        restarted_catalog = await restarted_client.get("/api/v1/sessions")
    assert fault.status_code == 503
    assert fault.json()["error"] == "capture_fault"
    assert repeated.status_code == 503
    selected = next(
        item
        for item in catalog.json()["sessions"]
        if item["id"] == fixture.selected_session_id
    )
    assert selected["projection_status"] == "fault"
    assert selected["projection_gaps"] == ["capture_fault"]
    assert selected["event_count"] is None
    restarted_selected = next(
        item
        for item in restarted_catalog.json()["sessions"]
        if item["id"] == fixture.selected_session_id
    )
    assert restarted_selected["projection_status"] == "fault"


async def test_completed_cold_flight_revalidates_a_post_bootstrap_append(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=3)
    context = _client(fixture, tmp_path)
    async with context as client:
        first = await client.get(f"/api/v1/sessions/{fixture.selected_session_id}")
        assert first.status_code == 202
        resources = context.app.state.read_resources
        assert resources is not None
        for _attempt in range(500):
            if fixture.selected_session_id not in resources._pending_materializations:
                break
            await asyncio.sleep(0.001)
        else:
            raise AssertionError("cold materialization did not complete")
        before = resources.index.checkpoint(fixture.selected_session_id)
        assert before is not None
        with (fixture.selected_session_dir / "agent.jsonl").open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    {
                        "session_id": fixture.selected_session_id,
                        "player_id": "alpha",
                        "phase": "reasoning",
                        "text": "post bootstrap append",
                        "at": "2026-08-01T00:10:00+00:00",
                    }
                )
                + "\n"
            )
        second = await client.get(f"/api/v1/sessions/{fixture.selected_session_id}")
    assert second.status_code == 200
    assert second.json()["totals"]["records"] == before.record_count + 1


async def test_one_shot_materializations_retire_bounded_handler_state(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=30)
    context = _client(fixture, tmp_path)
    async with context as client:
        responses = await asyncio.gather(
            *(
                client.get(f"/api/v1/sessions/session-{index:03d}")
                for index in range(30)
            )
        )
        resources = context.app.state.read_resources
        assert resources is not None
        assert (
            len(resources._pending_materializations) <= resources.materializer.capacity
        )
        assert {response.status_code for response in responses} <= {202, 503}
        for _attempt in range(2_000):
            if not resources._pending_materializations:
                break
            await asyncio.sleep(0.001)
        else:
            raise AssertionError("completed one-shot materializations were retained")
        assert not resources._materialization_cleanups


async def test_experiment_identities_change_only_with_contributing_data(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=4)
    _link_experiment_samples(fixture)
    async with _client(fixture, tmp_path) as client:
        for session_id in ("session-000", "session-001"):
            assert (
                await _await_ready(client, f"/api/v1/sessions/{session_id}")
            ).status_code == 200
            assert (
                await client.get(f"/api/v1/sessions/{session_id}/goals")
            ).status_code == 200
        first_catalog = await client.get("/api/v1/experiments")
        first_detail = await client.get("/api/v1/experiments/experiment-a")
        unchanged = await client.get("/api/v1/experiments")

        with sqlite3.connect(fixture.config_dir / "registry.db") as database:
            database.execute(
                """
                UPDATE sessions
                SET experiment_id = 'experiment-a', run_id = 'sample-c'
                WHERE session_id = 'session-002'
                """
            )
        assert (
            await _await_ready(client, "/api/v1/sessions/session-002")
        ).status_code == 200
        assert (
            await client.get("/api/v1/sessions/session-002/goals")
        ).status_code == 200
        changed_catalog = await client.get("/api/v1/experiments")
        changed_detail = await client.get("/api/v1/experiments/experiment-a")

    assert first_catalog.json()["source_cursor"] == unchanged.json()["source_cursor"]
    assert (
        first_catalog.json()["source_cursor"]
        != (changed_catalog.json()["source_cursor"])
    )
    assert (
        first_detail.json()["source_cursor"] != changed_detail.json()["source_cursor"]
    )
    assert changed_catalog.json()["experiments"][0]["sample_count"] == 3
    assert (
        "experiment_definitions_unavailable" in (changed_catalog.json()["capture_gaps"])
    )
    assert changed_detail.json()["aggregates"]["samples"] == 3
    assert changed_detail.json()["definition"] is None


async def test_unknown_scoped_identities_are_typed_not_found(
    tmp_path: Path,
) -> None:
    fixture, _digest = _resource_fixture(tmp_path)
    session_id = fixture.selected_session_id
    paths = (
        f"/api/v1/sessions/{session_id}/goals/unknown/turns",
        f"/api/v1/sessions/{session_id}/turns/unknown/iterations",
        f"/api/v1/sessions/{session_id}/evidence/unknown/children",
        f"/api/v1/sessions/{session_id}/traces/unknown",
        f"/api/v1/sessions/{session_id}/cost?scope_id=unknown",
    )
    async with _client(fixture, tmp_path) as client:
        await client.get(f"/api/v1/sessions/{session_id}")
        responses = [await client.get(path) for path in paths]
    assert {response.status_code for response in responses} == {404}
    assert {response.json()["error"] for response in responses} == {"not_found"}


async def test_large_retained_fields_obey_hard_response_byte_limits(
    tmp_path: Path,
) -> None:
    fixture, _digest = _resource_fixture(tmp_path)
    source = fixture.selected_session_dir / "agent.jsonl"
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "session_id": fixture.selected_session_id,
                    "player_id": "alpha",
                    "phase": "response",
                    "text": "x" * (300 * 1024),
                    "at": "2026-08-01T00:10:00+00:00",
                }
            )
            + "\n"
        )
    with sqlite3.connect(fixture.config_dir / "registry.db") as database:
        database.execute(
            "UPDATE sessions SET character = ? WHERE session_id = ?",
            ("c" * (100 * 1024), fixture.selected_session_id),
        )
        database.execute(
            """
            INSERT INTO lifecycle (session_id, at, state, detail)
            VALUES (?, '2026-08-01T00:11:00+00:00', 'observing', ?)
            """,
            (
                fixture.selected_session_id,
                json.dumps({"detail": "l" * (300 * 1024)}),
            ),
        )
        lifecycle_sequence = int(
            database.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
    _write_knowledge(fixture.config_dir)
    knowledge_value = {"detail": "k" * (300 * 1024)}
    with sqlite3.connect(
        fixture.config_dir / "profiles" / "alpha" / "knowledge.db"
    ) as database:
        database.execute(
            "UPDATE assertions SET value_json = ? WHERE assertion_id = 'assertion-0'",
            (json.dumps(knowledge_value),),
        )
    async with _client(fixture, tmp_path) as client:
        catalog = await client.get("/api/v1/sessions?limit=3")
        summary = await _await_ready(
            client,
            f"/api/v1/sessions/{fixture.selected_session_id}",
        )
        live = await client.get(
            f"/api/v1/live/{fixture.selected_session_id}/thought-activity"
        )
        search = await client.get(
            f"/api/v1/sessions/{fixture.selected_session_id}/search",
            params={"q": "xxxx"},
        )
        index_source = fixture.config_dir / "observatory" / "index-v1.sqlite3"
        with sqlite3.connect(index_source) as database:
            record_id = str(
                database.execute(
                    """
                    SELECT entity_id FROM evidence_payloads
                    WHERE session_id = ? AND evidence_kind = 'agent:response'
                    ORDER BY rowid DESC LIMIT 1
                    """,
                    (fixture.selected_session_id,),
                ).fetchone()[0]
            )
        evidence = await client.get(
            f"/api/v1/sessions/{fixture.selected_session_id}/evidence/{record_id}"
        )
        evidence_content = await _reconstruct_content(
            client,
            (
                f"/api/v1/sessions/{fixture.selected_session_id}"
                f"/evidence/{record_id}/content"
            ),
        )
        lifecycle_content = await _reconstruct_content(
            client,
            (
                f"/api/v1/sessions/{fixture.selected_session_id}"
                f"/lifecycle/{lifecycle_sequence}/content"
            ),
        )
        knowledge_content = await _reconstruct_content(
            client,
            "/api/v1/knowledge/alpha/assertions/assertion-0/content",
        )
    assert len(catalog.content) < 64 * 1024
    assert "registry_character_truncated" in catalog.json()["capture_gaps"]
    assert len(summary.content) < 64 * 1024
    assert "registry_character_truncated" in summary.json()["capture_gaps"]
    assert len(live.content) < 128 * 1024
    assert "live_values_truncated" in live.json()["capture_gaps"]
    assert len(search.content) < 256 * 1024
    assert len(evidence.content) < 256 * 1024
    assert "evidence_fields_truncated" in evidence.json()["capture_gaps"]
    assert json.loads(evidence_content)["text"] == "x" * (300 * 1024)
    assert json.loads(lifecycle_content)["detail"] == "l" * (300 * 1024)
    assert json.loads(knowledge_content) == knowledge_value


async def test_representative_resource_performance_and_payload_budgets(
    tmp_path: Path,
    record_testsuite_property: Callable[[str, object], None],
) -> None:
    fixture = _representative_fixture(tmp_path)
    session_id = fixture.selected_session_id
    record_id = stable_entity_id(session_id, "record", "agent:2")
    async with _client(fixture, tmp_path) as client:
        cold: dict[str, float] = {}
        responses: dict[str, httpx.Response] = {}
        cold_responses: dict[str, httpx.Response] = {}
        for name, path in (
            ("catalog", "/api/v1/sessions?limit=50"),
            ("summary", f"/api/v1/sessions/{session_id}"),
            ("hierarchy", f"/api/v1/sessions/{session_id}/goals"),
            ("evidence", f"/api/v1/sessions/{session_id}/evidence/{record_id}"),
        ):
            started = time.perf_counter()
            responses[name] = await client.get(path)
            cold_responses[name] = responses[name]
            cold[name] = (time.perf_counter() - started) * 1_000

        live_path = f"/api/v1/live/{session_id}/world-map"
        assert (await client.get(live_path)).status_code == 200
        index_source = fixture.config_dir / "observatory" / "index-v1.sqlite3"
        with sqlite3.connect(index_source) as database:
            checkpoint = database.execute(
                """
                SELECT s.record_count, w.agent_offset, w.gateway_sequence
                FROM sessions AS s
                JOIN source_watermarks AS w USING (session_id)
                WHERE s.session_id = ?
                """,
                (session_id,),
            ).fetchone()
        assert checkpoint is not None
        assert checkpoint[0] >= 7_000
        assert (
            checkpoint[1]
            == (fixture.selected_session_dir / "agent.jsonl").stat().st_size
        )
        with sqlite3.connect(
            fixture.selected_session_dir / "gateway.db"
        ) as gateway_database:
            gateway_rows = gateway_database.execute(
                "SELECT COUNT(*), MAX(seq) FROM events"
            ).fetchone()
        assert gateway_rows == (2_000, checkpoint[2])
        responses["evidence"] = await client.get(
            f"/api/v1/sessions/{session_id}/evidence/{record_id}"
        )
        warm: dict[str, list[float]] = {
            "catalog": [],
            "summary": [],
            "hierarchy": [],
            "live": [],
        }
        warm_paths = {
            "catalog": "/api/v1/sessions?limit=50",
            "summary": f"/api/v1/sessions/{session_id}",
            "hierarchy": f"/api/v1/sessions/{session_id}/goals",
            "live": live_path,
        }
        for name, path in warm_paths.items():
            await client.get(path)
            for _sample in range(20):
                started = time.perf_counter()
                responses[name] = await client.get(path)
                warm[name].append((time.perf_counter() - started) * 1_000)

        delays: list[float] = []

        async def ticker() -> None:
            previous = time.perf_counter()
            for _sample in range(40):
                await asyncio.sleep(0.001)
                current = time.perf_counter()
                delays.append((current - previous - 0.001) * 1_000)
                previous = current

        await asyncio.gather(
            ticker(),
            *(client.get(live_path) for _request in range(16)),
        )

    assert cold_responses["catalog"].status_code == 200
    assert cold_responses["catalog"].json()["completeness"] == "partial"
    selected = next(
        item
        for item in cold_responses["catalog"].json()["sessions"]
        if item["id"] == session_id
    )
    assert selected["projection_status"] == "pending"
    # Before materialization the catalog reads no retained journal, so
    # the event figure is honestly absent.
    assert selected["event_count"] is None
    for name in ("summary", "hierarchy", "evidence"):
        assert cold_responses[name].status_code == 202
        assert cold_responses[name].json()["state"] == "materialization_pending"
        assert cold_responses[name].json()["capture_gaps"] == [
            "materialization_pending"
        ]
    assert responses["catalog"].status_code == 200
    assert responses["catalog"].json()["completeness"] == "partial"
    selected_after = next(
        item
        for item in responses["catalog"].json()["sessions"]
        if item["id"] == session_id
    )
    assert selected_after["projection_status"] == "available"
    assert selected_after["event_count"] is not None
    assert responses["summary"].status_code == 200
    assert responses["summary"].json()["totals"]["records"] >= 7_000
    assert responses["hierarchy"].status_code == 200
    assert responses["hierarchy"].json()["items"]
    assert responses["evidence"].status_code == 200
    assert responses["evidence"].json()["record"]["id"] == record_id
    record_testsuite_property(
        "representative_resource_latency_ms",
        json.dumps(
            {
                "cold_ack": cold,
                "event_loop_delay_p95": _nearest_rank_p95(delays),
                "warm": {
                    name: {
                        "median": median(samples),
                        "p95": _nearest_rank_p95(samples),
                    }
                    for name, samples in warm.items()
                },
            },
            sort_keys=True,
        ),
    )
    assert len(responses["catalog"].content) < 64 * 1024
    assert len(responses["summary"].content) < 64 * 1024
    assert len(responses["hierarchy"].content) < 256 * 1024
    assert len(responses["evidence"].content) < 256 * 1024
    assert len(responses["live"].content) < 128 * 1024


def _resource_fixture(root: Path) -> tuple[RetainedFixture, str]:
    fixture = build_retained_fixture(root, session_count=3)
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
            "phase": "model_input",
            "model": "test-model",
            "model_visible_input": "structured city street",
            "at": "2026-08-01T00:00:03+00:00",
        },
        {
            **identity,
            "phase": "reasoning",
            "text": "Check the north gate",
            "at": "2026-08-01T00:00:04+00:00",
        },
        {
            **identity,
            "phase": "response",
            "model": "test-model",
            "text": "I found the route",
            "tokens": 321,
            "cost_usd": 0.0123,
            "duration_ms": 420,
            "at": "2026-08-01T00:00:05+00:00",
        },
    ]
    (fixture.selected_session_dir / "agent.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    wire_body = b"raw telnet body before transformation and display"
    digest = sha256(wire_body).hexdigest()
    gateway_source = fixture.selected_session_dir / "gateway.db"
    with sqlite3.connect(gateway_source) as database:
        database.execute("DELETE FROM events")
        database.executemany(
            """
            INSERT INTO events (
                session, at, monotonic, kind, trace_id, payload
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    fixture.selected_gateway_session_id,
                    1.0,
                    1.0,
                    "wire_text",
                    "trace-1",
                    json.dumps(
                        {
                            "text": "raw mud text",
                            "digest": digest,
                            "redacted": False,
                        }
                    ),
                ),
                (
                    fixture.selected_gateway_session_id,
                    2.0,
                    2.0,
                    "parser_input",
                    "trace-1",
                    json.dumps({"text": "raw mud text"}),
                ),
                (
                    fixture.selected_gateway_session_id,
                    3.0,
                    3.0,
                    "observation",
                    "trace-1",
                    json.dumps(
                        {
                            "text": "structured city street",
                            "place_id": "place:57",
                            "title": "City Street",
                            "exits": ["north", "south"],
                            "x": 3,
                            "y": 4,
                        }
                    ),
                ),
            ],
        )
        database.execute(
            "INSERT INTO blobs (digest, body) VALUES (?, ?)",
            (digest, wire_body),
        )
    return fixture, digest


def _link_experiment_samples(fixture: RetainedFixture) -> None:
    with sqlite3.connect(fixture.config_dir / "registry.db") as database:
        database.execute(
            """
            UPDATE sessions
            SET experiment_id = 'experiment-a', run_id = 'sample-a'
            WHERE session_id = 'session-000'
            """
        )
        database.execute(
            """
            UPDATE sessions
            SET experiment_id = 'experiment-a', run_id = 'sample-b'
            WHERE session_id = 'session-001'
            """
        )


def _write_knowledge(config_dir: Path) -> None:
    source = config_dir / "profiles" / "alpha" / "knowledge.db"
    with sqlite3.connect(source) as database:
        database.executescript(KNOWLEDGE_SCHEMA)
        for index in range(2):
            fact_id = f"fact-{index}"
            assertion_id = f"assertion-{index}"
            database.execute(
                """
                INSERT INTO facts (
                    fact_id, subject, predicate, layer,
                    current_assertion_id, created_at
                ) VALUES (?, ?, ?, 'learned', ?, ?)
                """,
                (
                    fact_id,
                    f"place:{index}",
                    "title",
                    assertion_id,
                    float(index),
                ),
            )
            database.execute(
                """
                INSERT INTO assertions (
                    assertion_id, fact_id, value_json, value_digest,
                    status, confidence, method, parser_version,
                    session_id, source_seq, wire_digest, observed_at,
                    supersedes, conflict_group, transaction_id
                ) VALUES (
                    ?, ?, ?, ?, 'active', 'observed', 'parser', 'v1',
                    'session-000', ?, ?, ?, NULL, NULL, ?
                )
                """,
                (
                    assertion_id,
                    fact_id,
                    json.dumps(f"Room {index}"),
                    sha256(f"Room {index}".encode()).hexdigest(),
                    index + 1,
                    "0" * 64,
                    float(index),
                    f"tx-{index}",
                ),
            )
            database.execute(
                """
                INSERT INTO evidence_refs (
                    assertion_id, session_id, source_seq, wire_digest,
                    parser_version, method, observed_at
                ) VALUES (?, 'session-000', ?, ?, 'v1', 'parser', ?)
                """,
                (assertion_id, index + 1, "0" * 64, float(index)),
            )
            database.execute(
                """
                INSERT INTO changes (
                    transaction_id, operation, entity_type, entity_id,
                    before_digest, after_digest, session_id, source_seq, at
                ) VALUES (?, 'assert', 'assertion', ?, NULL, ?,
                          'session-000', ?, ?)
                """,
                (
                    f"tx-{index}",
                    assertion_id,
                    sha256(assertion_id.encode()).hexdigest(),
                    index + 1,
                    float(index),
                ),
            )


def _representative_fixture(root: Path) -> RetainedFixture:
    return build_readiness_fixture(root).retained


class _ClientContext:
    def __init__(self, fixture: RetainedFixture, root: Path) -> None:
        self.app = create_app(
            Settings(
                runtime_root=fixture.config_dir,
                web_dist=root / "web",
            )
        )
        self.client: httpx.AsyncClient | None = None
        self.lifespan: Any = None

    async def __aenter__(self) -> httpx.AsyncClient:
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://observatory",
        )
        await self.client.__aenter__()
        return self.client

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        assert self.client is not None
        await self.client.__aexit__(exception_type, exception, traceback)
        await self.lifespan.__aexit__(exception_type, exception, traceback)


def _client(fixture: RetainedFixture, root: Path) -> _ClientContext:
    return _ClientContext(fixture, root)


def _nearest_rank_p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, int(len(ordered) * 0.95 + 0.9999) - 1)]


async def _reconstruct_content(
    client: httpx.AsyncClient,
    path: str,
) -> bytes:
    offset = 0
    retained = bytearray()
    expected_digest: str | None = None
    while True:
        response = await client.get(
            path,
            params={"offset": offset, "max_bytes": 8_192},
        )
        assert response.status_code == 200
        assert len(response.content) < 16 * 1024
        value = response.json()
        if expected_digest is None:
            expected_digest = value["content_digest"]
        assert value["content_digest"] == expected_digest
        assert value["offset"] == offset
        retained.extend(base64.b64decode(value["chunk"]))
        next_offset = value["next_offset"]
        if next_offset is None:
            assert len(retained) == value["total_bytes"]
            break
        offset = next_offset
    assert sha256(retained).hexdigest() == expected_digest
    return bytes(retained)


async def _await_ready(
    client: httpx.AsyncClient,
    path: str,
) -> httpx.Response:
    response = await client.get(path)
    for _attempt in range(200):
        if response.status_code != 202:
            assert response.status_code == 200
            return response
        await asyncio.sleep(0.005)
        response = await client.get(path)
    raise AssertionError("materialization did not converge")


async def _await_terminal_response(
    client: httpx.AsyncClient,
    path: str,
) -> httpx.Response:
    response = await client.get(path)
    for _attempt in range(200):
        if response.status_code != 202:
            return response
        await asyncio.sleep(0.005)
        response = await client.get(path)
    raise AssertionError("materialization did not reach a terminal response")


async def test_catalog_merges_configured_players_with_start_available(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=2)
    async with _client(fixture, tmp_path) as client:
        response = await client.get("/api/v1/sessions")
    assert response.status_code == 200
    players = {item["id"]: item for item in response.json()["players"]}
    # A gateway-configured identity with no live session is offered for Start,
    # carrying only public fields, never a secret.
    assert "default" in players
    assert players["default"]["start_available"] is True
    assert set(players["default"]) == {"id", "label", "start_available"}
    # The session-derived player is still present.
    assert "alpha" in players


async def test_catalog_reads_only_registry_and_index(tmp_path: Path) -> None:
    """The catalog never opens retained session files.

    A materialized session keeps its indexed objective and counts after
    every retained file disappears, and a never-materialized session
    lists as pending with a null objective instead of a journal replay.
    """
    fixture = build_retained_fixture(tmp_path, session_count=2)
    session_id = fixture.selected_session_id
    async with _client(fixture, tmp_path) as client:
        await _await_ready(client, f"/api/v1/sessions/{session_id}")
        for name in ("agent.jsonl", "gateway.db", "operator-messages.json"):
            retained = fixture.selected_session_dir / name
            if retained.exists():
                retained.unlink()
        response = await client.get("/api/v1/sessions")

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()["sessions"]}
    materialized = by_id[session_id]
    assert materialized["projection_status"] == "available"
    assert materialized["objective"] is not None
    assert materialized["turn_count"] is not None
    assert materialized["event_count"] == materialized["latest_seq"]
    assert materialized["goal_count"] is None
    assert materialized["nudge_count"] is None
    pending = next(item for item in by_id.values() if item["id"] != session_id)
    assert pending["projection_status"] == "pending"
    assert pending["objective"] is None
    assert pending["event_count"] is None
