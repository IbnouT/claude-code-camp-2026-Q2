"""Durability and safety gates for lifecycle commands."""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from observatory_v3_backend.app import create_app
from observatory_v3_backend.commands import (
    Command,
    CommandConflictError,
    CommandService,
    CommandStore,
    CommandSubmission,
    CommandUnavailableError,
)
from observatory_v3_backend.commands.effects import RuntimeCommandEffects
from observatory_v3_backend.settings import Settings
from observatory_v3_backend.sources.runtime import RuntimeSourceError

from .fixtures import build_retained_fixture


class FakeEffects:
    """Deterministic command effects with explicit recovery evidence."""

    def __init__(self) -> None:
        self.applied: list[str] = []
        self.recovered: list[str] = []
        self.validated: list[str] = []

    def validate(self, value: CommandSubmission) -> None:
        self.validated.append(value.idempotency_key)

    def apply(self, command: Command) -> str | None:
        self.applied.append(command.id)
        return command.session_id

    def reconcile(self, command: Command) -> str | None:
        self.recovered.append(command.id)
        return command.session_id


def submission(**changes: Any) -> CommandSubmission:
    value = CommandSubmission(
        idempotency_key="request-key-0001",
        action="guide",
        actor="operator",
        player_id="player-a",
        session_id="session-a",
        expected_cursor="session-a:7",
        instruction="Inspect the eastern gate.",
    )
    return replace(value, **changes)


async def terminal(service: CommandService, command_id: str) -> Command:
    for _ in range(100):
        command = await service.get(command_id)
        if command.terminal:
            return command
        await asyncio.sleep(0)
    raise AssertionError("command did not reach a terminal state")


@pytest.mark.asyncio
async def test_idempotency_returns_one_command_and_applies_once(
    tmp_path: Path,
) -> None:
    store = CommandStore(tmp_path)
    effects = FakeEffects()
    service = CommandService(store, effects)
    await service.start()

    first = await service.submit(submission())
    duplicate = await service.submit(submission())
    result = await terminal(service, first.id)

    assert duplicate.id == first.id
    assert result.state == "succeeded"
    assert effects.applied == [first.id]
    assert effects.validated == ["request-key-0001"]
    await service.close()
    store.close()


class RejectingEffects(FakeEffects):
    def validate(self, value: CommandSubmission) -> None:
        super().validate(value)
        raise RuntimeSourceError("the selected session belongs to another player")


@pytest.mark.asyncio
async def test_invalid_authority_returns_conflict_before_persistence(
    tmp_path: Path,
) -> None:
    store = CommandStore(tmp_path)
    effects = RejectingEffects()
    service = CommandService(store, effects)
    await service.start()

    with pytest.raises(CommandConflictError, match="another player"):
        await service.submit(submission())

    assert store.recoverable() == ()
    assert effects.applied == []
    await service.close()
    store.close()


@pytest.mark.asyncio
async def test_idempotency_key_rejects_a_different_mutation(tmp_path: Path) -> None:
    store = CommandStore(tmp_path)
    service = CommandService(store, FakeEffects())
    await service.start()
    await service.submit(submission())

    with pytest.raises(CommandConflictError):
        await service.submit(submission(action="pause", instruction=None))

    await service.close()
    store.close()


@pytest.mark.asyncio
async def test_restart_recovers_persisted_running_command(tmp_path: Path) -> None:
    store = CommandStore(tmp_path)
    command, _ = store.submit(submission())
    store.transition(command.id, "running")
    store.close()

    reopened = CommandStore(tmp_path)
    effects = FakeEffects()
    service = CommandService(reopened, effects)
    await service.start()
    result = await terminal(service, command.id)

    assert result.state == "succeeded"
    assert effects.recovered == [command.id]
    await service.close()
    reopened.close()


class FakeSession:
    id = "session-a"
    player_id = "player-a"


class FakeRuntime:
    def __init__(self) -> None:
        self.controlled = False

    def session(self, _session_id: str) -> FakeSession:
        return FakeSession()

    def control(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        self.controlled = True
        raise RuntimeSourceError("stale cursor")

    def process_id(self, _session_id: str, *, player_id: str) -> int:
        assert player_id == "player-a"
        return 321


class RecoveredRuntime(FakeRuntime):
    def control(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        self.controlled = True
        return {"ok": True}


def command(**changes: Any) -> Command:
    value = Command(
        id="command-a",
        idempotency_key="request-key-0001",
        action="guide",
        actor="operator",
        player_id="player-a",
        session_id="session-a",
        expected_cursor="session-a:7",
        instruction="Look east.",
        force=False,
        state="running",
        submitted_at="2026-08-03T00:00:00+00:00",
        started_at=None,
        finished_at=None,
        result_code=None,
        result_detail=None,
        result_session_id=None,
    )
    return replace(value, **changes)


def test_player_isolation_precedes_operator_socket_delivery(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    with pytest.raises(RuntimeSourceError, match="another player"):
        effects.apply(command(player_id="player-b"))

    assert runtime.controlled is False


def test_stale_cursor_failure_stays_inside_authenticated_boundary(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime()
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    with pytest.raises(RuntimeSourceError, match="stale cursor"):
        effects.apply(command())

    assert runtime.controlled is True


def test_restart_reuses_authenticated_operator_control(tmp_path: Path) -> None:
    runtime = RecoveredRuntime()
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    session_id = effects.reconcile(command())

    assert session_id == "session-a"
    assert runtime.controlled is True


def test_forced_stop_rejects_an_unverified_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr("os.getpgid", lambda _pid: 999)
    monkeypatch.setattr(
        "os.killpg",
        lambda process_group, signal_number: signalled.append(
            (process_group, signal_number)
        ),
    )
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    with pytest.raises(RuntimeSourceError, match="cannot be verified"):
        effects.apply(
            command(
                action="stop",
                instruction=None,
                force=True,
            )
        )

    assert signalled == []


@pytest.mark.asyncio
async def test_start_returns_202_and_status_is_bounded(tmp_path: Path) -> None:
    effects = FakeEffects()
    application = create_app(
        Settings(runtime_root=tmp_path, web_dist=tmp_path),
        command_effects=effects,
    )
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            response = await client.post(
                "/api/v1/commands/start",
                json={
                    "idempotency_key": "start-request-0001",
                    "actor": "operator",
                    "player_id": "player-a",
                    "instruction": "Map the eastern road.",
                },
            )
            assert response.status_code == 202
            command_id = response.json()["command_id"]
            status = await client.get(f"/api/v1/commands/{command_id}")

    assert status.status_code == 200
    assert status.json()["resource_id"] == f"command:{command_id}"
    assert "instruction" not in status.json()


@pytest.mark.asyncio
async def test_locked_store_does_not_block_event_loop_or_leak_sqlite(
    tmp_path: Path,
) -> None:
    store = CommandStore(tmp_path)
    service = CommandService(store, FakeEffects())
    await service.start()
    blocker = sqlite3.connect(store.path)
    blocker.execute("BEGIN IMMEDIATE")
    ticks = 0
    ticking = True

    async def ticker() -> None:
        nonlocal ticks
        while ticking:
            ticks += 1
            await asyncio.sleep(0.005)

    ticker_task = asyncio.create_task(ticker())
    try:
        with pytest.raises(
            CommandUnavailableError,
            match="storage is unavailable",
        ):
            await service.submit(submission(idempotency_key="locked-request-01"))
    finally:
        ticking = False
        await ticker_task
        blocker.rollback()
        blocker.close()

    assert ticks >= 5
    await service.close()
    store.close()


@pytest.mark.asyncio
async def test_locked_store_returns_typed_api_503(tmp_path: Path) -> None:
    application = create_app(
        Settings(runtime_root=tmp_path, web_dist=tmp_path / "web"),
        command_effects=FakeEffects(),
    )
    async with application.router.lifespan_context(application):
        blocker = sqlite3.connect(tmp_path / "observatory" / "commands-v1.sqlite3")
        blocker.execute("BEGIN IMMEDIATE")
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application),
                base_url="http://observatory",
            ) as client:
                response = await client.post(
                    "/api/v1/commands/start",
                    json={
                        "idempotency_key": "locked-api-request",
                        "actor": "operator",
                        "player_id": "alpha",
                    },
                )
        finally:
            blocker.rollback()
            blocker.close()

    assert response.status_code == 503
    assert response.json()["error"] == "command_unavailable"
    assert response.json()["detail"] == "durable command storage is unavailable"


class FirstStartEffects(FakeEffects):
    """Create retained runtime sources only when the first effect runs."""

    def __init__(self, staging: Path, runtime_root: Path) -> None:
        super().__init__()
        self.staging = staging
        self.staging.mkdir()
        self.runtime_root = runtime_root
        self._lock = threading.Lock()
        self.session_id: str | None = None

    def apply(self, command: Command) -> str | None:
        with self._lock:
            if self.session_id is None:
                fixture = build_retained_fixture(self.staging, session_count=1)
                shutil.copytree(
                    fixture.config_dir,
                    self.runtime_root,
                    dirs_exist_ok=True,
                )
                with sqlite3.connect(self.runtime_root / "registry.db") as database:
                    rows = database.execute(
                        "SELECT session_id, player_id FROM sessions"
                    ).fetchall()
                    for session_id, player_id in rows:
                        session_dir = (
                            self.runtime_root
                            / "profiles"
                            / str(player_id)
                            / "sessions"
                            / str(session_id)
                        )
                        database.execute(
                            """
                            UPDATE sessions
                            SET session_dir = ?, manifest_path = ?
                            WHERE session_id = ?
                            """,
                            (
                                str(session_dir),
                                str(session_dir / "session.json"),
                                session_id,
                            ),
                        )
                self.session_id = fixture.selected_session_id
        return self.session_id


@pytest.mark.asyncio
async def test_concurrent_first_starts_attach_read_services_once(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    effects = FirstStartEffects(tmp_path / "staging", runtime_root)
    application = create_app(
        Settings(runtime_root=runtime_root, web_dist=tmp_path / "web"),
        command_effects=effects,
    )
    async with application.router.lifespan_context(application):
        assert application.state.read_resources is None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://observatory",
        ) as client:
            responses = await asyncio.gather(
                client.post(
                    "/api/v1/commands/start",
                    json={
                        "idempotency_key": "first-start-alpha",
                        "actor": "operator",
                        "player_id": "alpha",
                    },
                ),
                client.post(
                    "/api/v1/commands/start",
                    json={
                        "idempotency_key": "first-start-beta",
                        "actor": "operator",
                        "player_id": "beta",
                    },
                ),
            )
            command_ids = [response.json()["command_id"] for response in responses]
            for command_id in command_ids:
                for _ in range(100):
                    status = await client.get(f"/api/v1/commands/{command_id}")
                    if status.json()["state"] == "succeeded":
                        break
                    await asyncio.sleep(0.01)
                assert status.json()["state"] == "succeeded"
            attached_resources = application.state.read_resources
            sessions = await client.get("/api/v1/sessions")

        assert sessions.status_code == 200
        assert application.state.read_resources is attached_resources
        assert application.state.session_materializer is not None
        notifications = application.state.session_notifications
        assert notifications is not None
        assert effects.session_id is not None
        lease = await notifications.acquire(effects.session_id)
        await lease.close()
