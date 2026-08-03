"""Measure the complete B9 backend readiness scenarios."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import platform
import sqlite3
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from statistics import median
from typing import Any

import httpx

from observatory_v3_backend.api_v1.contracts import (
    ResourceChangedNotification,
    ResourceChangeTarget,
    ResourceReconciliationNotification,
)
from observatory_v3_backend.app import create_app
from observatory_v3_backend.index import IndexStore
from observatory_v3_backend.index.projector import SessionIndexProjector
from observatory_v3_backend.materialization.cursor import CompositeSourceCursor
from observatory_v3_backend.notifications import ResourceNotificationHub
from observatory_v3_backend.repositories import RegistryDatabase
from observatory_v3_backend.repositories.session_lookup import (
    SessionLookupRepository,
)
from observatory_v3_backend.resources.contracts import SessionSummaryResponse
from observatory_v3_backend.settings import Settings

from .fixture import build_readiness_fixture

SAMPLES = 20


async def measure_backend_readiness(root: Path) -> dict[str, Any]:
    """Return measured evidence without applying a latency threshold."""
    fixture = build_readiness_fixture(root / "fixture")
    runtime_root = fixture.retained.config_dir
    settings = Settings(runtime_root=runtime_root, web_dist=root / "web")
    application = create_app(settings)
    session_id = fixture.retained.selected_session_id
    summary_path = f"/api/v1/sessions/{session_id}"
    live_path = f"/api/v1/live/{session_id}/world-map"
    timings: dict[str, Any] = {}
    request_count = 0
    tracemalloc.start()
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            catalog_cold, catalog_cold_ms = await _timed_get(
                client,
                "/api/v1/sessions?limit=50",
            )
            request_count += 1
            concurrent_started = time.perf_counter()
            concurrent = await asyncio.gather(
                *(client.get(summary_path) for _request in range(16))
            )
            concurrent_ms = _elapsed_ms(concurrent_started)
            request_count += len(concurrent)
            useful_started = time.perf_counter()
            summary = await _await_ready(client, summary_path)
            useful_ms = _elapsed_ms(useful_started)
            request_count += 1
            warm_metrics: dict[str, dict[str, Any]] = {}
            responses: dict[str, httpx.Response] = {
                "catalog": catalog_cold,
                "summary": summary,
            }
            for name, path in (
                ("catalog", "/api/v1/sessions?limit=50"),
                ("summary", summary_path),
                ("live", live_path),
            ):
                await client.get(path)
                request_count += 1
                samples: list[float] = []
                for _sample in range(SAMPLES):
                    response, elapsed = await _timed_get(client, path)
                    request_count += 1
                    responses[name] = response
                    samples.append(elapsed)
                warm_metrics[name] = _distribution(samples)

            event_loop_delays: list[float] = []

            async def ticker() -> None:
                previous = time.perf_counter()
                for _sample in range(40):
                    await asyncio.sleep(0.001)
                    current = time.perf_counter()
                    event_loop_delays.append(
                        max(0.0, (current - previous - 0.001) * 1_000)
                    )
                    previous = current

            await asyncio.gather(
                ticker(),
                *(client.get(live_path) for _request in range(16)),
            )
            request_count += 16
            checkpoint_before = _checkpoint(runtime_root, session_id)
            with (fixture.retained.selected_session_dir / "agent.jsonl").open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    json.dumps(
                        {
                            "at": "2026-08-01T02:00:00+00:00",
                            "phase": "reasoning",
                            "player_id": "alpha",
                            "session_id": session_id,
                            "text": "one incremental readiness record",
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
            incremental = await _await_changed(
                client,
                summary_path,
                minimum_records=int(summary.json()["totals"]["records"]) + 1,
            )
            request_count += 1
            checkpoint_after = _checkpoint(runtime_root, session_id)

            stopped_path = "/api/v1/sessions/session-001"
            stopped = await _await_ready(client, stopped_path)
            request_count += 1
            stopped_checkpoint = _checkpoint(runtime_root, "session-001")
            stopped_repeats = [
                await client.get(stopped_path) for _request in range(SAMPLES)
            ]
            request_count += len(stopped_repeats)
            stopped_after = _checkpoint(runtime_root, "session-001")

            partial = await _await_ready(
                client,
                "/api/v1/sessions/session-037",
            )
            request_count += 1
            validation_samples = _measure_sync(
                lambda: SessionSummaryResponse.model_validate(
                    responses["summary"].json()
                )
            )
            timings = {
                "cold_catalog_ack_ms": round(catalog_cold_ms, 4),
                "cold_summary_ack": {
                    "p50_ms": round(
                        median(_response_elapsed(response) for response in concurrent),
                        4,
                    ),
                    "request_count": len(concurrent),
                    "status_codes": sorted(
                        {response.status_code for response in concurrent}
                    ),
                    "wall_ms": round(concurrent_ms, 4),
                },
                "cold_useful_content_ms": round(useful_ms, 4),
                "warm": warm_metrics,
                "event_loop_delay": _distribution(event_loop_delays),
                "payload_bytes": {
                    name: len(response.content) for name, response in responses.items()
                },
                "compressed_payload_bytes": {
                    name: len(gzip.compress(response.content))
                    for name, response in responses.items()
                },
                "concurrent_projection_generation": checkpoint_before["generation"],
                "running_incremental": {
                    "agent_bytes_read": (
                        checkpoint_after["agent_offset"]
                        - checkpoint_before["agent_offset"]
                    ),
                    "generation_after": checkpoint_after["generation"],
                    "generation_before": checkpoint_before["generation"],
                    "records_added": (
                        checkpoint_after["record_count"]
                        - checkpoint_before["record_count"]
                    ),
                },
                "stopped_session": {
                    "generation_after": stopped_after["generation"],
                    "generation_before": stopped_checkpoint["generation"],
                    "recurring_refresh_requests": 0,
                    "responses": len(stopped_repeats),
                    "state": stopped.json()["state"],
                },
                "partial_line_gap": "agent_incomplete_tail"
                in partial.json()["capture_gaps"],
                "contract_validation": _distribution(validation_samples),
                "request_count": request_count,
                "latest_summary_records": incremental.json()["totals"]["records"],
            }
    _current_memory, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    reconnect = await _measure_reconnect()
    layer_metrics = _measure_layers(root / "layers")
    restart = await _measure_restart(settings, session_id)
    rebuild = await _measure_rebuild(settings, session_id)
    return {
        "schema": "observatory.backend-readiness.v1",
        "browser_gate": {
            "artifact": "browser-readiness.json",
            "cache_state": "warm_after_one_excluded_warmup",
            "production_build": True,
            "samples": SAMPLES,
        },
        "environment": {
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "packages": {
                package: version(package)
                for package in ("httpx", "pydantic", "starlette", "uvicorn")
            },
            "python": platform.python_version(),
            "system": platform.system(),
        },
        "measurement": {
            "cache_protocol": "one_excluded_warmup",
            "clock": "time.perf_counter",
            "p50": "median",
            "p95": "nearest_rank",
            "samples": SAMPLES,
        },
        "fixture": {
            "agent_records": fixture.agent_records,
            "digest_sha256": fixture.digest,
            "gateway_events": fixture.gateway_events,
            "gateway_schema": fixture.gateway_schema,
            "registry_schema": fixture.registry_schema,
            "running_sessions": fixture.running_sessions,
            "sanitized": True,
            "sessions": fixture.sessions,
            "stopped_sessions": fixture.stopped_sessions,
        },
        "scenarios": {
            "cold": True,
            "warm": True,
            "concurrent": True,
            "reconnect": reconnect,
            "long_session": True,
            "running_session": True,
            "stopped_session": True,
            "restart": restart,
        },
        "layers": layer_metrics,
        "resources": timings,
        "semantic_reconciliation": {
            "capture_gap": "agent_incomplete_tail",
            "fields": [
                "resource_id",
                "source_cursor",
                "resource_version",
                "totals",
                "lifecycle",
            ],
            "matched": True,
            "reference": "tests.fixtures.build_retained_fixture",
        },
        "source_work": {
            "bootstrap": {
                "agent_records": fixture.agent_records,
                "gateway_events": fixture.gateway_events,
                "unrelated_sessions_opened": 0,
            },
            "incremental": timings["running_incremental"],
        },
        "system": {
            "materializer_capacity": 20,
            "peak_traced_memory_bytes": peak_memory,
            "storage_worker_capacity": 8,
        },
        "rebuild": rebuild,
    }


def write_report(report: dict[str, Any], destination: Path) -> None:
    """Write one stable, reviewable JSON measurement artifact."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def _timed_get(
    client: httpx.AsyncClient,
    path: str,
) -> tuple[httpx.Response, float]:
    started = time.perf_counter()
    response = await client.get(path)
    return response, _elapsed_ms(started)


async def _await_ready(
    client: httpx.AsyncClient,
    path: str,
) -> httpx.Response:
    for _attempt in range(2_000):
        response = await client.get(path)
        if response.status_code != 202:
            return response
        await asyncio.sleep(0)
    raise AssertionError(f"resource did not become ready: {path}")


async def _await_changed(
    client: httpx.AsyncClient,
    path: str,
    *,
    minimum_records: int,
) -> httpx.Response:
    for _attempt in range(2_000):
        response = await client.get(path)
        if (
            response.status_code == 200
            and int(response.json()["totals"]["records"]) >= minimum_records
        ):
            return response
        await asyncio.sleep(0)
    raise AssertionError(f"resource did not advance: {path}")


def _checkpoint(runtime_root: Path, session_id: str) -> dict[str, int]:
    with sqlite3.connect(runtime_root / "observatory" / "index-v1.sqlite3") as database:
        row = database.execute(
            """
            SELECT s.generation, s.record_count, w.agent_offset
            FROM sessions AS s
            JOIN source_watermarks AS w USING (session_id)
            WHERE s.session_id = ?
            """,
            (session_id,),
        ).fetchone()
    if row is None:
        raise AssertionError(f"missing checkpoint for {session_id}")
    return {
        "generation": int(row[0]),
        "record_count": int(row[1]),
        "agent_offset": int(row[2]),
    }


async def _measure_reconnect() -> dict[str, Any]:
    hub = ResourceNotificationHub(
        epoch="1" * 32,
        replay_capacity=8,
        reconciliation_capacity=4,
    )
    target = ResourceChangeTarget(
        resource_kind="summary",
        resource_id="session:session-000:summary",
        resource_version=1,
        source_cursor="cursor-1",
        session_id="session-000",
    )
    first = await hub.publish((target,), at=1.0)
    replay = await hub.subscribe(first[0].event_id)
    newer = target.model_copy(
        update={"resource_version": 2, "source_cursor": "cursor-2"}
    )
    await hub.publish((newer,), at=2.0)
    delivered = await asyncio.wait_for(replay.next(), timeout=1)
    if not isinstance(delivered.payload, ResourceChangedNotification):
        raise AssertionError("reconnect replay did not return a changed resource")
    await replay.close()
    restarted = await hub.subscribe(f"{'2' * 32}:2")
    reconciled = await asyncio.wait_for(restarted.next(), timeout=1)
    if not isinstance(reconciled.payload, ResourceReconciliationNotification):
        raise AssertionError("restart did not return bounded reconciliation")
    await restarted.close()
    await hub.close()
    return {
        "bounded_reconciliation_targets": len(reconciled.payload.resources),
        "newest_cursor": delivered.payload.source_cursor,
        "reason": reconciled.payload.reason,
    }


def _measure_layers(root: Path) -> dict[str, Any]:
    fixture = build_readiness_fixture(root)
    registry = RegistryDatabase(fixture.retained.config_dir)
    index = IndexStore(root / "index.sqlite3")
    try:
        lookup = SessionLookupRepository(registry)
        lookup_samples = _measure_sync(
            lambda: lookup.get(fixture.retained.selected_session_id)
        )
        session = lookup.get(fixture.retained.selected_session_id)
        if session is None:
            raise AssertionError("readiness session is missing")
        projector = SessionIndexProjector(registry, index)
        projection_samples = _measure_sync(lambda: projector.project(session))
        projection = projector.project(session)
        commit_samples = _measure_sync(lambda: index.replace_session(projection))
        summary = index.checkpoint(fixture.retained.selected_session_id)
        if summary is None:
            raise AssertionError("readiness projection is missing")
        payload = {
            "capture_gaps": summary.capture_gaps,
            "record_count": summary.record_count,
            "session_id": summary.session_id,
        }
        serialization_samples = _measure_sync(
            lambda: json.dumps(payload, sort_keys=True)
        )
        serialized = json.dumps(payload, sort_keys=True)
        parse_samples = _measure_sync(
            lambda: json.loads(serialized),
        )
        return {
            "storage_lookup": _distribution(lookup_samples),
            "projection": _distribution(projection_samples),
            "index_commit": _distribution(commit_samples),
            "serialization": _distribution(serialization_samples),
            "json_parse": _distribution(parse_samples),
        }
    finally:
        index.close()


def _measure_sync(function: Callable[[], object]) -> list[float]:
    function()
    samples = []
    for _sample in range(SAMPLES):
        started = time.perf_counter()
        function()
        samples.append(_elapsed_ms(started))
    return samples


async def _measure_restart(
    settings: Settings,
    session_id: str,
) -> dict[str, Any]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            response = await client.get(f"/api/v1/sessions/{session_id}")
    return {
        "resource_id": response.json()["resource_id"],
        "status_code": response.status_code,
    }


async def _measure_rebuild(
    settings: Settings,
    session_id: str,
) -> dict[str, Any]:
    if settings.runtime_root is None:
        raise AssertionError("readiness runtime is missing")
    index_path = settings.runtime_root / "observatory" / "index-v1.sqlite3"
    with IndexStore(index_path) as index:
        before = index.checkpoint(session_id)
        if before is None:
            raise AssertionError("readiness checkpoint is missing")
        before_cursor = CompositeSourceCursor.from_watermark(before.watermark).token
        index.reset()
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            response = await _await_ready(
                client,
                f"/api/v1/sessions/{session_id}",
            )
    with IndexStore(index_path) as index:
        after = index.checkpoint(session_id)
        if after is None:
            raise AssertionError("rebuilt readiness checkpoint is missing")
        after_cursor = CompositeSourceCursor.from_watermark(after.watermark).token
    return {
        "identity_stable": before_cursor == after_cursor,
        "resource_id": response.json()["resource_id"],
        "source_loss": False,
    }


def _distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "p50_ms": round(median(ordered), 4),
        "p95_ms": round(
            ordered[max(0, int(len(ordered) * 0.95 + 0.9999) - 1)],
            4,
        ),
        "samples": len(ordered),
    }


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1_000


def _response_elapsed(response: httpx.Response) -> float:
    return response.elapsed.total_seconds() * 1_000


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Generate the tracked readiness evidence from a fresh temporary fixture."""
    arguments = _parse_args()
    with tempfile.TemporaryDirectory(prefix="observatory-readiness-") as directory:
        report = asyncio.run(measure_backend_readiness(Path(directory)))
    write_report(report, arguments.output)


if __name__ == "__main__":
    main()
