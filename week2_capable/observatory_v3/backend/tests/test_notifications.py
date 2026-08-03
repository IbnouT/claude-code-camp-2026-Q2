"""SSE replay, coalescing, bounds, and committed-target gates."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import StreamingResponse

from observatory_v3_backend.api_v1.contracts import (
    ResourceChangedNotification,
    ResourceChangeTarget,
    ResourceNotification,
    ResourceReconciliationNotification,
)
from observatory_v3_backend.app import create_app
from observatory_v3_backend.commands import Command, CommandSubmission
from observatory_v3_backend.notifications import (
    NotificationSubscriberLimitError,
    ResourceNotificationHub,
)
from observatory_v3_backend.notifications.service import (
    SessionNotificationService,
)
from observatory_v3_backend.notifications.transport import (
    _session_filter,
    session_notification_response,
)
from observatory_v3_backend.settings import Settings

from .fixtures import build_retained_fixture

BACKEND_ROOT = Path(__file__).resolve().parents[1]
EPOCH = "0123456789abcdef0123456789abcdef"


class BlockingCommandEffects:
    """Hold one command after running publication until the test releases it."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def validate(self, _value: CommandSubmission) -> None:
        return

    def apply(self, command: Command) -> str | None:
        self.release.wait(timeout=2)
        return command.session_id

    def reconcile(self, command: Command) -> str | None:
        return self.apply(command)


async def test_cursor_coalescing_and_inside_epoch_replay() -> None:
    hub = ResourceNotificationHub(epoch=EPOCH, replay_capacity=8)
    first = _target("summary", "session:s1:summary", 1, "cursor-1")
    newer = _target("summary", "session:s1:summary", 2, "cursor-2")

    initial = await hub.publish((first,), at=1.0)
    duplicate = await hub.publish((first,), at=2.0)
    latest = await hub.publish((newer,), at=3.0)
    subscription = await hub.subscribe(initial[0].event_id)
    replayed = await asyncio.wait_for(subscription.next(), timeout=1)

    assert duplicate == ()
    assert latest[0].payload.change_counter == 2
    assert isinstance(replayed.payload, ResourceChangedNotification)
    assert replayed.payload.source_cursor == "cursor-2"
    assert replayed.event_id == f"{EPOCH}:2"
    await subscription.close()
    await hub.close()


async def test_experiment_notifications_cross_selected_session_filter() -> None:
    hub = ResourceNotificationHub(epoch=EPOCH, replay_capacity=8)
    experiment = _target(
        "experiment_job",
        "experiment-job:job-1",
        1,
        "cursor-experiment",
    )
    unrelated = _target(
        "summary",
        "session:other:summary",
        1,
        "cursor-other",
    )
    live = await hub.subscribe(
        None,
        target_filter=_session_filter("selected"),
    )
    published = await hub.publish((experiment, unrelated), at=1.0)
    delivered = await asyncio.wait_for(live.next(), timeout=1)
    assert isinstance(delivered.payload, ResourceChangedNotification)
    assert delivered.payload.resource_kind == "experiment_job"
    await live.close()

    replay = await hub.subscribe(
        f"{EPOCH}:0",
        target_filter=_session_filter("selected"),
    )
    replayed = await asyncio.wait_for(replay.next(), timeout=1)

    assert len(published) == 2
    assert isinstance(replayed.payload, ResourceChangedNotification)
    assert replayed.payload.resource_kind == "experiment_job"
    await replay.close()
    reconciliation = await hub.subscribe(
        f"{'f' * 32}:2",
        target_filter=_session_filter("selected"),
    )
    reconciled = await asyncio.wait_for(reconciliation.next(), timeout=1)
    assert isinstance(reconciled.payload, ResourceReconciliationNotification)
    assert [target.resource_kind for target in reconciled.payload.resources] == [
        "experiment_job"
    ]
    await reconciliation.close()
    await hub.close()


async def test_epoch_mismatch_gets_one_bounded_reconciliation() -> None:
    hub = ResourceNotificationHub(
        epoch=EPOCH,
        reconciliation_capacity=2,
    )
    await hub.publish(
        (
            _target("summary", "session:s1:summary", 1, "cursor-1"),
            _target("goals", "session:s1:goals:root", 1, "cursor-1"),
            _target("map", "session:s1:map", 1, "cursor-1"),
        ),
        at=1.0,
    )
    subscription = await hub.subscribe(f"{'f' * 32}:3")
    reconciled = await asyncio.wait_for(subscription.next(), timeout=1)

    assert isinstance(reconciled.payload, ResourceReconciliationNotification)
    assert reconciled.payload.reason == "epoch_mismatch"
    assert reconciled.payload.change_counter == 3
    assert len(reconciled.payload.resources) == 2
    assert [item.resource_kind for item in reconciled.payload.resources] == [
        "goals",
        "map",
    ]
    await subscription.close()
    await hub.close()


async def test_slow_consumer_uses_shared_bounded_replay_and_newest_cursor() -> None:
    hub = ResourceNotificationHub(
        epoch=EPOCH,
        replay_capacity=3,
        reconciliation_capacity=4,
    )
    subscription = await hub.subscribe(f"{EPOCH}:0")
    for version in range(1, 11):
        await hub.publish(
            (
                _target(
                    "summary",
                    "session:s1:summary",
                    version,
                    f"cursor-{version}",
                ),
            ),
            at=float(version),
        )
    reconciled = await asyncio.wait_for(subscription.next(), timeout=1)

    assert hub.history_size == 3
    assert isinstance(reconciled.payload, ResourceReconciliationNotification)
    assert reconciled.payload.reason == "replay_window_exhausted"
    assert len(reconciled.payload.resources) == 1
    assert reconciled.payload.resources[0].source_cursor == "cursor-10"
    await subscription.close()
    await hub.close()


async def test_subscribers_and_mandatory_publications_remain_bounded() -> None:
    hub = ResourceNotificationHub(
        epoch=EPOCH,
        subscriber_capacity=2,
    )
    first = await hub.subscribe(None)
    second = await hub.subscribe(None)
    with pytest.raises(NotificationSubscriberLimitError):
        await hub.subscribe(None)

    target = _target("control_receipt", "session:s1:receipt:r1", 1, "cursor-1")
    published = await hub.publish((target,), force=True, at=1.0)
    repeated = await hub.publish((target,), force=True, at=2.0)

    assert hub.subscriber_count == 2
    assert published[0].payload.change_counter == 1
    assert repeated[0].payload.change_counter == 2
    await first.close()
    await second.close()
    assert hub.subscriber_count == 0
    await hub.close()


async def test_sse_frame_targets_are_readable_before_delivery(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web",
        )
    )
    async with application.router.lifespan_context(application):
        request = _request(
            application,
            session_id=fixture.selected_session_id,
        )
        hub = cast(
            ResourceNotificationHub,
            application.state.resource_notification_hub,
        )
        service = cast(
            SessionNotificationService,
            application.state.session_notifications,
        )
        response = await session_notification_response(
            request,
            hub=hub,
            service=service,
        )
        assert isinstance(response, StreamingResponse)
        body = cast(AsyncGenerator[bytes, None], response.body_iterator)
        frame = await asyncio.wait_for(anext(body), timeout=2)
        payload = _frame_payload(frame)
        notification = ResourceNotification.model_validate(payload).root

        assert isinstance(notification, ResourceChangedNotification)
        assert notification.server_epoch == hub.epoch
        resources = application.state.read_resources.resources
        readable = await application.state.read_resources.storage.run(
            _readable_targets,
            resources,
            fixture.selected_session_id,
        )
        catalog_target = (
            await application.state.read_resources.notification_catalog_target()
        )
        readable.add(
            (
                catalog_target.resource_kind,
                catalog_target.resource_id,
                catalog_target.resource_version,
                catalog_target.source_cursor,
            )
        )
        assert (
            notification.resource_kind,
            notification.resource_id,
            notification.resource_version,
            notification.source_cursor,
        ) in readable

        await body.aclose()
        await _wait_for_teardown(hub, service)
        assert hub.subscriber_count == 0
        assert service.active_session_count == 0


async def test_session_sse_delivers_queued_running_and_terminal_commands(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    effects = BlockingCommandEffects()
    application = create_app(
        Settings(runtime_root=fixture.config_dir, web_dist=tmp_path / "web"),
        command_effects=effects,
    )
    async with application.router.lifespan_context(application):
        hub = cast(
            ResourceNotificationHub,
            application.state.resource_notification_hub,
        )
        service = cast(
            SessionNotificationService,
            application.state.session_notifications,
        )
        seed = await service.acquire(fixture.selected_session_id)
        await seed.wait_ready()
        baseline = hub.change_counter
        await seed.close()
        response = await session_notification_response(
            _request(
                application,
                session_id=fixture.selected_session_id,
                last_event_id=f"{hub.epoch}:{baseline}",
            ),
            hub=hub,
            service=service,
        )
        body = cast(AsyncGenerator[bytes, None], response.body_iterator)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            accepted = await client.post(
                f"/api/v1/sessions/{fixture.selected_session_id}/commands",
                json={
                    "idempotency_key": "notification-command-01",
                    "actor": "operator",
                    "player_id": "alpha",
                    "action": "pause",
                    "expected_cursor": "opaque-test-cursor",
                },
            )
            assert accepted.status_code == 202
            queued = _frame_payload(await asyncio.wait_for(anext(body), timeout=2))
            running = _frame_payload(await asyncio.wait_for(anext(body), timeout=2))
            effects.release.set()
            terminal = _frame_payload(await asyncio.wait_for(anext(body), timeout=2))
            command_id = accepted.json()["command_id"]
            readable = await client.get(f"/api/v1/commands/{command_id}")

        payloads = tuple(
            ResourceNotification.model_validate(value).root
            for value in (queued, running, terminal)
        )
        assert all(isinstance(value, ResourceChangedNotification) for value in payloads)
        changed = cast(
            tuple[ResourceChangedNotification, ...],
            payloads,
        )
        assert [value.source_cursor.split(":", 1)[0] for value in changed] == [
            "queued",
            "running",
            "succeeded",
        ]
        assert all(
            value.resource_id == f"command:{accepted.json()['command_id']}"
            for value in changed
        )
        assert all(value.session_id == fixture.selected_session_id for value in changed)
        assert readable.status_code == 200
        await body.aclose()
        await _wait_for_teardown(hub, service)


async def test_cold_unsupported_schema_records_and_publishes_readable_fault(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    with sqlite3.connect(fixture.selected_session_dir / "gateway.db") as database:
        database.execute("PRAGMA user_version=999")
    application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web",
        )
    )
    async with application.router.lifespan_context(application):
        hub = cast(
            ResourceNotificationHub,
            application.state.resource_notification_hub,
        )
        service = cast(
            SessionNotificationService,
            application.state.session_notifications,
        )
        response = await session_notification_response(
            _request(application, session_id=fixture.selected_session_id),
            hub=hub,
            service=service,
        )
        body = cast(AsyncGenerator[bytes, None], response.body_iterator)
        notification = ResourceNotification.model_validate(
            _frame_payload(await asyncio.wait_for(anext(body), timeout=2))
        ).root
        catalog_response = await application.state.read_resources.session_catalog(
            _request(application, session_id=fixture.selected_session_id)
        )
        catalog = json.loads(bytes(catalog_response.body))
        selected = next(
            item
            for item in catalog["sessions"]
            if item["id"] == fixture.selected_session_id
        )

        assert isinstance(notification, ResourceChangedNotification)
        assert notification.resource_kind == "session_catalog"
        assert notification.resource_id == catalog["resource_id"]
        assert notification.resource_version == catalog["resource_version"]
        assert notification.source_cursor == catalog["source_cursor"]
        assert selected["projection_status"] == "fault"
        assert selected["projection_gaps"] == ["capture_fault"]
        assert (
            application.state.session_index.materialization_fault(
                fixture.selected_session_id
            )
            == "Selected-session materialization failed validation."
        )
        assert (
            application.state.session_index.checkpoint(fixture.selected_session_id)
            is None
        )
        assert hub.change_counter == 1
        assert hub.history_size == 1

        await body.aclose()
        await _wait_for_teardown(hub, service)


async def test_true_restart_seeds_targets_before_epoch_reconciliation(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    first_application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web-first",
        )
    )
    async with first_application.router.lifespan_context(first_application):
        first_hub = cast(
            ResourceNotificationHub,
            first_application.state.resource_notification_hub,
        )
        first_service = cast(
            SessionNotificationService,
            first_application.state.session_notifications,
        )
        first_response = await session_notification_response(
            _request(
                first_application,
                session_id=fixture.selected_session_id,
            ),
            hub=first_hub,
            service=first_service,
        )
        first_body = cast(AsyncGenerator[bytes, None], first_response.body_iterator)
        first_frame = await asyncio.wait_for(anext(first_body), timeout=2)
        prior_event_id = _frame_event_id(first_frame)
        prior_epoch = first_hub.epoch
        await first_body.aclose()
        await _wait_for_teardown(first_hub, first_service)

    restarted_application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web-restarted",
        )
    )
    async with restarted_application.router.lifespan_context(restarted_application):
        restarted_hub = cast(
            ResourceNotificationHub,
            restarted_application.state.resource_notification_hub,
        )
        restarted_service = cast(
            SessionNotificationService,
            restarted_application.state.session_notifications,
        )
        restarted_response = await session_notification_response(
            _request(
                restarted_application,
                session_id=fixture.selected_session_id,
                last_event_id=prior_event_id,
            ),
            hub=restarted_hub,
            service=restarted_service,
        )
        restarted_body = cast(
            AsyncGenerator[bytes, None],
            restarted_response.body_iterator,
        )
        reconciliation = ResourceNotification.model_validate(
            _frame_payload(await asyncio.wait_for(anext(restarted_body), timeout=2))
        ).root

        assert restarted_hub.epoch != prior_epoch
        assert isinstance(
            reconciliation,
            ResourceReconciliationNotification,
        )
        assert reconciliation.reason == "epoch_mismatch"
        assert reconciliation.change_counter == 14
        assert len(reconciliation.resources) == 14
        assert {target.resource_kind for target in reconciliation.resources} == {
            "session_catalog",
            "session_summary",
            "lifecycle",
            "goals",
            "map",
            "cost",
            "live_partition",
        }

        await restarted_body.aclose()
        await _wait_for_teardown(restarted_hub, restarted_service)


async def test_notification_route_returns_typed_404_422_and_503(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web",
        )
    )
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            missing_query = await client.get("/api/v1/notifications")
            unknown_session = await client.get(
                "/api/v1/notifications",
                params={"session_id": "absent-session"},
            )

    unavailable = create_app(Settings(web_dist=tmp_path / "web-unavailable"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=unavailable),
        base_url="http://observatory",
    ) as client:
        missing_runtime = await client.get(
            "/api/v1/notifications",
            params={"session_id": fixture.selected_session_id},
        )

    assert missing_query.status_code == 422
    assert missing_query.json() == {
        "contract_version": "v1",
        "error": "invalid_request",
        "detail": "session_id must contain between 1 and 200 characters",
    }
    assert unknown_session.status_code == 404
    assert unknown_session.json() == {
        "contract_version": "v1",
        "error": "not_found",
        "detail": "The selected session does not exist.",
    }
    assert missing_runtime.status_code == 503
    assert missing_runtime.json() == {
        "contract_version": "v1",
        "error": "source_unavailable",
        "detail": "The retained session notification source is unavailable.",
    }


async def test_multiple_tabs_share_one_watcher_and_rapid_evidence_converges(
    tmp_path: Path,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web",
        )
    )
    async with application.router.lifespan_context(application):
        hub = cast(
            ResourceNotificationHub,
            application.state.resource_notification_hub,
        )
        service = cast(
            SessionNotificationService,
            application.state.session_notifications,
        )
        first = await service.acquire(fixture.selected_session_id)
        second = await service.acquire(fixture.selected_session_id)
        await _wait_for_counter(hub, 14)
        baseline = hub.change_counter

        assert baseline == 14
        assert service.active_session_count == 1

        subscription = await hub.subscribe(f"{hub.epoch}:{baseline}")
        with (fixture.selected_session_dir / "agent.jsonl").open(
            "a",
            encoding="utf-8",
        ) as source:
            for index in range(20):
                source.write(
                    json.dumps(
                        {
                            "session_id": fixture.selected_session_id,
                            "player_id": "alpha",
                            "phase": "reasoning",
                            "text": f"rapid-{index}",
                        }
                    )
                    + "\n"
                )
        await asyncio.gather(
            *(service.source_changed(fixture.selected_session_id) for _ in range(20))
        )
        newest = await _next_resource_kind(subscription, "session_summary")

        assert isinstance(newest.payload, ResourceChangedNotification)
        assert newest.payload.resource_kind == "session_summary"
        assert baseline < hub.change_counter <= baseline + 14
        summary = await application.state.read_resources.storage.run(
            application.state.read_resources.resources.session_summary,
            fixture.selected_session_id,
        )
        assert newest.payload.source_cursor == summary.source_cursor
        assert newest.payload.resource_version == summary.resource_version

        await first.close()
        assert service.active_session_count == 1
        await second.close()
        await subscription.close()
        await _wait_for_teardown(hub, service)


@pytest.mark.parametrize("scenario", ["terminal", "capture_fault"])
async def test_terminal_and_capture_fault_changes_are_delivered(
    tmp_path: Path,
    scenario: str,
) -> None:
    fixture = build_retained_fixture(tmp_path, session_count=1)
    application = create_app(
        Settings(
            runtime_root=fixture.config_dir,
            web_dist=tmp_path / "web",
        )
    )
    async with application.router.lifespan_context(application):
        hub = cast(
            ResourceNotificationHub,
            application.state.resource_notification_hub,
        )
        service = cast(
            SessionNotificationService,
            application.state.session_notifications,
        )
        lease = await service.acquire(fixture.selected_session_id)
        await _wait_for_counter(hub, 14)
        baseline = hub.change_counter
        subscription = await hub.subscribe(f"{hub.epoch}:{baseline}")

        if scenario == "terminal":
            _stop_retained_session(fixture)
        else:
            (fixture.selected_session_dir / "agent.jsonl").write_text(
                '{"session_id":"session-000","player_id":"alpha",'
                '"phase":"prompt","text":"truncated"}\n',
                encoding="utf-8",
            )
        await service.source_changed(fixture.selected_session_id)
        delivered = await _next_resource_kind(subscription, "session_summary")
        summary = await application.state.read_resources.storage.run(
            application.state.read_resources.resources.session_summary,
            fixture.selected_session_id,
        )

        assert isinstance(delivered.payload, ResourceChangedNotification)
        assert delivered.payload.resource_kind == "session_summary"
        assert delivered.payload.resource_version == summary.resource_version
        if scenario == "terminal":
            assert summary.state == "stopped"
        else:
            assert summary.completeness == "degraded"
            assert "agent_source_truncated" in summary.capture_gaps

        await lease.close()
        await subscription.close()
        await _wait_for_teardown(hub, service)


def test_deterministic_notification_fixtures_match_transport_contract() -> None:
    fixture = BACKEND_ROOT / "openapi" / "fixtures" / "resource-notifications.json"
    values = json.loads(fixture.read_text(encoding="utf-8"))
    parsed = tuple(ResourceNotification.model_validate(value).root for value in values)

    assert isinstance(parsed[0], ResourceChangedNotification)
    assert isinstance(parsed[1], ResourceReconciliationNotification)
    assert parsed[1].resources[0].source_cursor == "obc1_fixture"


def _target(
    resource_kind: str,
    resource_id: str,
    resource_version: int,
    source_cursor: str,
) -> ResourceChangeTarget:
    return ResourceChangeTarget(
        resource_kind=resource_kind,
        resource_id=resource_id,
        resource_version=resource_version,
        source_cursor=source_cursor,
    )


def _request(
    application: Any,
    *,
    session_id: str,
    last_event_id: str | None = None,
) -> Request:
    query = urlencode({"session_id": session_id}).encode()
    headers = (
        () if last_event_id is None else ((b"last-event-id", last_event_id.encode()),)
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/notifications",
        "raw_path": b"/api/v1/notifications",
        "query_string": query,
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("observatory", 80),
        "root_path": "",
        "app": application,
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def _frame_payload(frame: bytes) -> dict[str, object]:
    lines = frame.decode().splitlines()
    data = next(line[6:] for line in lines if line.startswith("data: "))
    value = json.loads(data)
    assert isinstance(value, dict)
    return value


def _frame_event_id(frame: bytes) -> str:
    lines = frame.decode().splitlines()
    return next(line[4:] for line in lines if line.startswith("id: "))


def _readable_targets(
    resources: Any,
    session_id: str,
) -> set[tuple[str, str, int, str]]:
    from observatory_v3_backend.notifications.targets import (
        CommittedResourceTargets,
    )

    return {
        (
            target.resource_kind,
            target.resource_id,
            target.resource_version,
            target.source_cursor,
        )
        for target in CommittedResourceTargets(resources).for_session(session_id)
    }


async def _wait_for_teardown(
    hub: ResourceNotificationHub,
    service: SessionNotificationService,
) -> None:
    for _attempt in range(100):
        if hub.subscriber_count == 0 and service.active_session_count == 0:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("notification subscriber did not tear down")


async def _wait_for_counter(
    hub: ResourceNotificationHub,
    minimum: int,
) -> None:
    for _attempt in range(200):
        if hub.change_counter >= minimum:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("notification publication did not converge")


async def _next_resource_kind(
    subscription: Any,
    resource_kind: str,
) -> Any:
    for _attempt in range(14):
        envelope = await asyncio.wait_for(subscription.next(), timeout=2)
        if (
            isinstance(envelope.payload, ResourceChangedNotification)
            and envelope.payload.resource_kind == resource_kind
        ):
            return envelope
    raise AssertionError(f"notification kind {resource_kind!r} did not arrive")


def _stop_retained_session(fixture: Any) -> None:
    with sqlite3.connect(fixture.config_dir / "registry.db") as database:
        database.execute(
            """
            UPDATE sessions
            SET state = 'stopped',
                updated_at = '2026-08-01T02:00:00+00:00',
                ended_at = '2026-08-01T02:00:00+00:00',
                exit_code = 0,
                stop_mode = 'completed',
                pid = NULL
            WHERE session_id = ?
            """,
            (fixture.selected_session_id,),
        )
        database.execute(
            """
            INSERT INTO lifecycle (session_id, at, state, detail)
            VALUES (?, '2026-08-01T02:00:00+00:00', 'stopped', '{}')
            """,
            (fixture.selected_session_id,),
        )
