"""Recorded Sessions preserve correlations, provenance, and evidence gaps."""

from __future__ import annotations

import json
import sqlite3

import httpx

from backend.app import create_app
from backend.projections.session import (
    _objective,
    project_recorded_session,
    project_recorded_session_prefix,
)
from backend.settings import Settings
from backend.sources.recorded_session import RecordedSessionSource


def _fixture(tmp_path):
    root = tmp_path / "benchmarks"
    ledger = root / "j2-probe"
    attempt = ledger / "attempts" / "a1"
    attempt.mkdir(parents=True)
    record = {
        "attempt_id": "a1",
        "journey_id": "J2",
        "profile_id": "poucet",
        "success": False,
        "stop_reason": "completed",
        "iterations": 12,
        "cost_usd": 0.21,
        "cost_curve": [0.21],
        "result_mode": "full",
        "parse_misses": 2,
        "corrective_calls": 3,
        "invalid_calls": 0,
        "fresh_input_tokens": 900,
        "cache_read_tokens": 200,
        "cache_write_tokens": 50,
        "output_tokens": 80,
        "occupancy_tokens": 200,
    }
    (ledger / "attempts.jsonl").write_text(json.dumps(record) + "\n")
    agent_rows = [
        {
            "phase": "config",
            "session_id": "agent-1",
            "at": "2026-07-29T08:00:00Z",
            "task": "Find the minotaur",
            "model": "test-model",
        },
        {
            "phase": "iteration",
            "session_id": "agent-1",
            "at": "2026-07-29T08:00:01Z",
            "n": 12,
        },
        {
            "phase": "response",
            "session_id": "agent-1",
            "at": "2026-07-29T08:00:02Z",
            "text": "I am finished.",
            "stop_reason": "completed",
            "cost_usd": 0.05,
            "usage": {
                "input_tokens": 900,
                "cache_read_tokens": 200,
                "cache_write_tokens": 50,
                "output_tokens": 80,
            },
        },
        {
            "phase": "tool_call",
            "session_id": "agent-1",
            "at": "2026-07-29T08:00:03Z",
            "id": "tool-1",
            "name": "tbamud__move",
            "args": {"direction": "north"},
        },
        {
            "phase": "tool_result",
            "session_id": "agent-1",
            "at": "2026-07-29T08:00:04Z",
            "tool_use_id": "tool-1",
            "name": "tbamud__move",
            "ok": True,
            "result": json.dumps(
                {
                    "trace_id": "trace-1",
                    "text": "Duplicate Entrance",
                }
            ),
        },
    ]
    (attempt / "agent.jsonl").write_text(
        "\n".join(json.dumps(row) for row in agent_rows) + "\n"
    )
    database = attempt / "gateway.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE events ("
        "seq INTEGER PRIMARY KEY, session TEXT, at REAL, "
        "monotonic REAL, kind TEXT, trace_id TEXT, payload TEXT)"
    )
    gateway_rows = [
        (1, "gateway-1", 1, 1, "tool_call", "trace-1", {
            "tool": "move",
        }),
        (2, "gateway-1", 2, 2, "command", "trace-1", {
            "line": "north",
            "password": "private-value",
        }),
        (3, "gateway-1", 3, 3, "wire", "trace-1", {
            "direction": "in",
            "bytes": 42,
            "digest": "short-digest",
        }),
        (4, "gateway-1", 4, 4, "observation", "trace-1", {
            "kind": "room",
            "title": "Duplicate Entrance",
            "exits": ["south"],
            "text": "/Users/private/capture.txt",
        }),
        (5, "gateway-1", 5, 5, "position", "trace-1", {
            "place": 10,
            "title": "Duplicate Entrance",
            "confidence": "tracked",
            "method": "exits",
        }),
        (6, "gateway-1", 6, 6, "position", "trace-1", {
            "place": None,
            "title": "Duplicate Entrance",
            "confidence": "ambiguous",
            "method": "duplicate-title",
        }),
        (7, "gateway-1", 7, 7, "unparsed", "trace-1", {
            "text": "unknown fragment",
        }),
        (8, "gateway-1", 8, 8, "tool_result", "trace-1", {
            "tool": "move",
            "complete": True,
        }),
    ]
    connection.executemany(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (*row[:6], json.dumps(row[6]))
            for row in gateway_rows
        ],
    )
    connection.commit()
    connection.close()
    return root


def test_recorded_session_projection_is_correlated_navigable_and_sanitized(
    tmp_path,
):
    source = RecordedSessionSource(_fixture(tmp_path))
    catalog = source.catalog()
    assert len(catalog) == 1
    assert catalog[0].source_kind == "experiment_sample"
    assert catalog[0].player_id == "poucet"

    bundle = source.load(catalog[0].id)
    assert bundle is not None
    result = project_recorded_session(bundle)
    encoded = result.model_dump_json()
    records = {record.id: record for record in result.records}

    assert result.source_kind == "experiment_sample"
    assert result.objective == "Find the minotaur"
    assert result.agent_session_id == "agent-1"
    assert result.gateway_session_id == "gateway-1"
    assert records["gateway:1"].parent_id == "agent:4"
    assert records["agent:5"].parent_id == "gateway:8"
    assert records["gateway:2"].fields["password"] == "[REDACTED]"
    assert "[LOCAL_PATH]" in records["gateway:4"].fields["text"]
    assert "private-value" not in encoded
    assert "/Users/" not in encoded
    assert result.cost.complete
    assert result.cost.reconciliation_delta_usd == 0
    assert result.cost.raw_response_total_usd == 0.05
    assert result.cost.points[0].cost_usd == 0.21
    assert result.cost.points[0].pricing_source == "attempt_cost_curve"
    assert "MUD text transformation stages are missing" in result.capture_gaps
    assert "Exact model request body is missing" in result.capture_gaps
    assert "Exact provider response body is missing" in result.capture_gaps
    assert set(result.diagnostic_coverage) == {
        "false_completion",
        "belief_divergence",
        "position_ambiguity",
        "confusion_loop",
        "progress_stall",
        "parse_degradation",
        "corrective_call_cluster",
        "stale_action",
        "context_churn",
        "instrumentation_gap",
    }
    findings = {item.kind for item in result.diagnostics}
    assert {
        "false_completion",
        "belief_divergence",
        "position_ambiguity",
        "parse_degradation",
        "corrective_call_cluster",
        "context_churn",
    } <= findings
    assert all(item.evidence for item in result.diagnostics)


def test_incident_prefix_does_not_project_future_world_or_truth(tmp_path):
    source = RecordedSessionSource(_fixture(tmp_path))
    bundle = source.load(source.catalog()[0].id)
    assert bundle is not None

    result = project_recorded_session_prefix(bundle, "gateway:4")

    assert result.records[-1].id == "gateway:4"
    assert all(node.last_seq <= 4 for node in result.world.nodes)
    assert result.world.nodes == ()
    assert result.world.current_title is None
    assert result.lens.truth.state == "missing"
    assert result.cost.total_usd == 0
    assert not result.diagnostics


def test_prompt_evidence_supersedes_a_generic_agent_role():
    rows = (
        {"phase": "config", "task": "player"},
        {
            "phase": "prompt",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Find the Massive Minotaur.",
                        }
                    ],
                }
            ],
        },
    )

    assert _objective(rows) == "Find the Massive Minotaur."


async def test_recorded_session_routes_name_the_experiment_relationship(
    tmp_path,
):
    app = create_app(
        Settings(
            benchmark_root=_fixture(tmp_path),
            web_dist=tmp_path,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        catalog = await client.get("/api/recorded-sessions")
        run_id = catalog.json()["sessions"][0]["id"]
        detail = await client.get(f"/api/recorded-sessions/{run_id}")
        paused = await client.post(
            "/api/ask",
                json={
                    "question": "Why did the agent stop?",
                    "scope": {
                        "space": "sessions",
                        "run_id": run_id,
                        "selected_record_id": "agent:1",
                    },
                },
        )
        final = await client.post(
            "/api/ask",
                json={
                    "question": "Why did the agent stop?",
                    "scope": {
                        "space": "sessions",
                        "run_id": run_id,
                        "selected_record_id": "benchmark:outcome",
                    },
                },
        )
        search = await client.post(
            "/api/ask",
            json={
                "question": "Find gateway records",
                "scope": {
                    "space": "sessions",
                    "run_id": run_id,
                    "selected_record_id": "gateway:4",
                },
                "query": {
                    "version": 1,
                    "operation": "search_evidence",
                    "scope": {
                        "space": "sessions",
                        "run_id": run_id,
                        "selected_record_id": "gateway:4",
                    },
                    "filters": [
                        {
                            "field": "source",
                            "operator": "eq",
                            "value": "gateway",
                        }
                    ],
                    "order": "causal",
                    "limit": 25,
                },
            },
        )

    assert catalog.status_code == 200
    assert catalog.json()["sessions"][0]["source_kind"] == "experiment_sample"
    assert detail.status_code == 200
    assert detail.json()["correlation"].startswith(
        "This recorded session is linked"
    )
    assert paused.status_code == 200
    assert paused.json()["scope_record_id"] == "agent:1"
    assert "future evidence" in paused.json()["answer"]
    assert final.status_code == 200
    assert final.json()["claims"]
    assert "linked predicate remained false" in final.json()["answer"]
    assert search.status_code == 200
    assert [citation["id"] for citation in search.json()["citations"]] == [
        "gateway:1",
        "gateway:2",
        "gateway:3",
        "gateway:4",
    ]
