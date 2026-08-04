"""Durability and safety gates for lifecycle commands."""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import sqlite3
import subprocess
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
from observatory_v3_backend.commands import effects as effects_module
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
    latest_seq = 7


class FakeRuntime:
    def __init__(self) -> None:
        self.controlled = False
        self.stop_recorded: tuple[str, str] | None = None

    def record_stop(self, session_id: str, mode: str) -> None:
        self.stop_recorded = (session_id, mode)

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


class LiveFakeSession(FakeSession):
    live = True
    control_available = True
    latest_seq = 99


class SequenceRecordingRuntime(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.expected_sequence: int | None = None

    def session(self, _session_id: str) -> FakeSession:
        return LiveFakeSession()

    def control(self, *_args: object, **kwargs: object) -> dict[str, object]:
        self.controlled = True
        self.expected_sequence = kwargs["expected_sequence"]  # type: ignore[assignment]
        return {"ok": True}


def test_stop_cursor_is_advisory_and_delivers_current_sequence(
    tmp_path: Path,
) -> None:
    runtime = SequenceRecordingRuntime()
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]
    process = _StartProcess()
    effects._processes["session-a"] = process

    effects.validate(
        submission(action="stop", instruction=None, expected_cursor=None)
    )
    effects.apply(command(action="stop", instruction=None))

    assert runtime.controlled is True
    assert runtime.expected_sequence == 99
    assert runtime.stop_recorded == ("session-a", "cooperative")


def test_guide_cursor_still_guards_observed_state(tmp_path: Path) -> None:
    runtime = SequenceRecordingRuntime()
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    with pytest.raises(RuntimeSourceError, match="advanced"):
        effects.validate(submission(expected_cursor="session-a:7"))
    with pytest.raises(RuntimeSourceError, match="expected cursor"):
        effects.validate(submission(expected_cursor=None))

    assert runtime.controlled is False


def test_stop_escalates_a_process_that_refuses_to_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(effects_module, "STOP_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(effects_module, "STOP_FORCE_SECONDS", 2.0)
    runtime = SequenceRecordingRuntime()
    process = subprocess.Popen(["sleep", "120"], start_new_session=True)
    runtime.process_id = (  # type: ignore[method-assign]
        lambda session_id, *, player_id: process.pid
    )
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]
    effects._processes["session-a"] = process  # type: ignore[assignment]

    try:
        effects.apply(command(action="stop", instruction=None))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert process.poll() is not None
    assert runtime.stop_recorded == ("session-a", "forced_after_grace")


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


def _write_gateway_receipt(
    path: Path, kind: str, payload: dict[str, Any], *, seq: int = 1
) -> None:
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE IF NOT EXISTS events (seq INTEGER, kind TEXT, payload TEXT)"
        )
        database.execute(
            "INSERT INTO events (seq, kind, payload) VALUES (?, ?, ?)",
            (seq, kind, json.dumps(payload)),
        )
        database.commit()


def _write_control_state(session_dir: Path, state: str = "running") -> None:
    (session_dir / "control-state.json").write_text(
        json.dumps({"state": state}), encoding="utf-8"
    )


class _Record:
    """One lightweight registry row, as ``player_records`` returns."""

    def __init__(self, session_dir: Path, state: str = "running") -> None:
        self.session_id = "session-x"
        self.player_id = "player-a"
        self.state = state
        self.session_dir = session_dir

    @property
    def live(self) -> bool:
        return self.state in {"starting", "running", "draining", "quarantined"}


class _StagedRuntime:
    """No record before launch, then a running record whose control-state file
    is written only at the ``control_delay`` poll, like real startup."""

    def __init__(self, session_dir: Path, *, control_delay: int = 0) -> None:
        self._dir = session_dir
        self._control_delay = control_delay
        self.polls = 0
        self.launched = False

    def player_records(self, _player_id: str) -> tuple[_Record, ...]:
        if not self.launched:
            return ()
        if self.polls == self._control_delay:
            _write_control_state(self._dir, "running")
        self.polls += 1
        return (_Record(self._dir),)


class _StartProcess:
    def __init__(self) -> None:
        self.stdin = io.BytesIO()
        self.terminated = False

    def poll(self) -> int | None:
        return 0 if self.stdin.closed else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0


def test_control_state_running_reads_the_file(tmp_path: Path) -> None:
    assert effects_module._control_state_running(tmp_path) is False
    _write_control_state(tmp_path, "starting")
    assert effects_module._control_state_running(tmp_path) is False
    _write_control_state(tmp_path, "running")
    assert effects_module._control_state_running(tmp_path) is True


def test_reset_verified_requires_a_successful_receipt(tmp_path: Path) -> None:
    assert effects_module._reset_verified(tmp_path, "none") is True
    # No receipt yet: not ready, keep waiting.
    assert effects_module._reset_verified(tmp_path, "baseline") is False
    _write_gateway_receipt(tmp_path / "gateway.db", "reset_receipt", {"ok": True})
    assert effects_module._reset_verified(tmp_path, "baseline") is True


def test_reset_verified_rejects_a_failed_receipt(tmp_path: Path) -> None:
    _write_gateway_receipt(
        tmp_path / "gateway.db",
        "reset_receipt",
        {"ok": False, "error": "no baseline snapshot"},
    )
    with pytest.raises(RuntimeSourceError, match="no baseline snapshot"):
        effects_module._reset_verified(tmp_path, "baseline")


def test_start_builds_the_proven_agent_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _StagedRuntime(tmp_path)
    captured: dict[str, Any] = {}
    process = _StartProcess()

    def fake_popen(arguments: list[str], **kwargs: Any) -> _StartProcess:
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs
        runtime.launched = True
        return process

    monkeypatch.setattr(effects_module.subprocess, "Popen", fake_popen)
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    session_id = effects.apply(
        command(
            action="start",
            player_id="player-a",
            session_id=None,
            expected_cursor=None,
            instruction="Explore the eastern gate.",
            reset="none",
        )
    )

    assert session_id == "session-x"
    arguments = captured["arguments"]
    # The agent runs through its own uv project, never the backend interpreter.
    assert arguments[:3] == ["uv", "run", "--project"]
    assert arguments[3].endswith("week2_capable/agent")
    assert arguments[4] == "boukensha"
    assert arguments[5:7] == ["--no-tui", "--player-profile"]
    assert "--initial-task-stdin" in arguments
    assert "--task-stdin" not in arguments
    kwargs = captured["kwargs"]
    # stdin is always a pipe, and stderr is captured for failure reporting.
    assert kwargs["stdin"] == effects_module.subprocess.PIPE
    assert hasattr(kwargs["stderr"], "read")
    assert kwargs["cwd"] == str(Path(arguments[3]).parents[1])
    # The agent REPL exits on stdin EOF: the pipe stays open and the process
    # is retained for the session lifetime.
    assert process.stdin.closed is False
    assert process.stdin.getvalue() == b"Explore the eastern gate.\n"
    assert effects._processes["session-x"] is process


def test_start_baseline_reset_is_gated_on_its_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_gateway_receipt(tmp_path / "gateway.db", "reset_receipt", {"ok": True})
    runtime = _StagedRuntime(tmp_path)
    captured: dict[str, Any] = {}

    def fake_popen(arguments: list[str], **kwargs: Any) -> _StartProcess:
        captured["arguments"] = arguments
        runtime.launched = True
        return _StartProcess()

    monkeypatch.setattr(effects_module.subprocess, "Popen", fake_popen)
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    session_id = effects.apply(
        command(
            action="start",
            player_id="player-a",
            session_id=None,
            expected_cursor=None,
            instruction=None,
            reset="baseline",
        )
    )

    assert session_id == "session-x"
    arguments = captured["arguments"]
    assert arguments[arguments.index("--reset-baseline") + 1] == "level1-temple@1"


def test_start_waits_for_control_state_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _StagedRuntime(tmp_path, control_delay=2)

    def fake_popen(arguments: list[str], **kwargs: Any) -> _StartProcess:
        runtime.launched = True
        return _StartProcess()

    monkeypatch.setattr(effects_module.subprocess, "Popen", fake_popen)
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    session_id = effects.apply(
        command(
            action="start",
            player_id="player-a",
            session_id=None,
            expected_cursor=None,
            instruction=None,
            reset="none",
        )
    )

    assert session_id == "session-x"
    # It did not accept the first live appearance; it waited for control running.
    assert runtime.polls >= 3


def test_start_aborts_when_reset_receipt_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_gateway_receipt(
        tmp_path / "gateway.db",
        "reset_receipt",
        {"ok": False, "error": "baseline unavailable"},
    )
    runtime = _StagedRuntime(tmp_path)
    process = _StartProcess()

    def fake_popen(arguments: list[str], **kwargs: Any) -> _StartProcess:
        runtime.launched = True
        return process

    monkeypatch.setattr(effects_module.subprocess, "Popen", fake_popen)
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]

    with pytest.raises(RuntimeSourceError, match="baseline unavailable"):
        effects.apply(
            command(
                action="start",
                player_id="player-a",
                session_id=None,
                expected_cursor=None,
                instruction=None,
                reset="baseline",
            )
        )

    # A failed start is cleaned up and never retained.
    assert process.terminated is True
    assert "session-x" not in effects._processes


def test_stop_releases_the_retained_process(tmp_path: Path) -> None:
    runtime = RecoveredRuntime()
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]
    process = _StartProcess()
    effects._processes["session-a"] = process

    effects.apply(command(action="stop"))

    # Stop closes the retained stdin, reaps the process, and drops the handle.
    assert "session-a" not in effects._processes
    assert process.stdin.closed is True
    assert runtime.stop_recorded == ("session-a", "cooperative")


def test_guide_wakes_the_retained_idle_repl(tmp_path: Path) -> None:
    runtime = RecoveredRuntime()
    effects = RuntimeCommandEffects(tmp_path, runtime)  # type: ignore[arg-type]
    process = _StartProcess()
    effects._processes["session-a"] = process

    effects.apply(command(action="guide", instruction="Head north."))

    # An operator-message envelope nudges the idle REPL; the process is retained.
    assert b'"operator_message"' in process.stdin.getvalue()
    assert "session-a" in effects._processes
