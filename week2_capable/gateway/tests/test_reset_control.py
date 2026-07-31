from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from mud_gateway.baseline import LEVEL1_TEMPLE
from mud_gateway.journal import Journal
from mud_gateway.knowledge import EvidenceRef, KnowledgeStore
from mud_gateway.reset_control import (
    ControlRequest,
    ResetControlError,
    ResetControlServer,
    ResetCoordinator,
    _admin_environment,
)
from mud_gateway.session import Session, SessionPaused, SessionQuarantined
from mud_gateway.settings import GatewaySettings, PlayerProfile

SCORE = """You have 20(20) hit, 100(100) mana and 82(82) movement points.
Your armor class is 9/10, and your alignment is 0.
You have 0 exp, 0 gold coins, and 0 questpoints.
This ranks you as Tester the Swordpupil (level 1).
You are standing.
20H 100M 82V >"""

DIGEST = "a" * 64


class FakeSession:
    def __init__(self, journal: Journal) -> None:
        self.id = "gateway-1"
        self.name = "Tester"
        self.logged_in = True
        self.control_state = "running"
        self.journal = journal
        self.commands: list[str] = []
        self.reconnects = 0
        self.observations = SimpleNamespace(
            snapshot=lambda: SimpleNamespace(
                room=SimpleNamespace(
                    title="The Temple Of Midgaard",
                    exits=("n", "e", "s", "w", "d"),
                )
            )
        )

    @asynccontextmanager
    async def pause(self, *, timeout: float):
        assert timeout > 0
        self.control_state = "paused"
        try:
            yield
        finally:
            if self.control_state == "paused":
                self.control_state = "running"

    async def reset_command(self, line: str) -> SimpleNamespace:
        self.commands.append(line)
        return SimpleNamespace(text=SCORE if line == "score" else "")

    async def reconnect_for_reset(self) -> None:
        self.reconnects += 1

    def quarantine(self, reason: str) -> None:
        self.control_state = "quarantined"

    def allow_reset_retry(self) -> None:
        assert self.control_state == "quarantined"
        self.control_state = "running"


def make_settings(tmp_path: Path) -> GatewaySettings:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    socket_path = Path(tempfile.gettempdir()) / (
        "boukensha-test-"
        + hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]
        + ".sock"
    )
    manifest = {
        "schema_version": 1,
        "player_id": "tester",
        "character": "Tester",
        "agent_id": "agent-1",
        "session_id": "session-1",
        "gateway_session_id": "gateway-1",
        "configuration_digest": DIGEST,
        "control_socket": str(socket_path),
    }
    (session_dir / "session.json").write_text(json.dumps(manifest))
    (session_dir / "control.token").write_text("token-" + "x" * 24)
    return GatewaySettings(
        config_dir=tmp_path,
        player_profile="tester",
        players={
            "tester": PlayerProfile("tester", "Tester", "TESTER_PASSWORD")
        },
        journal=session_dir / "gateway.db",
        session_id="session-1",
        gateway_session_id="gateway-1",
        session_dir=session_dir,
        control_socket=socket_path,
    )


def request(settings: GatewaySettings, **changes: object) -> ControlRequest:
    values: dict[str, object] = {
        "protocol_version": 1,
        "request_id": "request-1",
        "action": "reset",
        "token": "token-" + "x" * 24,
        "expected_state": "running",
        "session_id": "session-1",
        "gateway_session_id": "gateway-1",
        "player_id": "tester",
        "character": "Tester",
        "baseline_id": LEVEL1_TEMPLE.id,
        "baseline_version": LEVEL1_TEMPLE.version,
        "expected_configuration_digest": DIGEST,
        "expected_sequence": 0,
        "nonce": "nonce-" + "y" * 24,
    }
    values.update(changes)
    return ControlRequest.model_validate(values)


async def test_reset_uses_selected_session_for_verification(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)
    child_requests: list[dict[str, object]] = []

    async def admin(
        payload: dict[str, object],
        _journal: Path,
        _progress: Path,
        _timeout: float,
    ) -> dict[str, object]:
        child_requests.append(payload)
        return {
            "ok": True,
            "applied": ("restore", "level", "transfer"),
            "located": (3001, "The Temple Of Midgaard"),
            "exit_status": 0,
        }

    try:
        coordinator = ResetCoordinator(
            settings,
            session=lambda: player,
            admin_runner=admin,
        )
        receipt = await coordinator.reset(request(settings))

        assert receipt["ok"] is True
        assert receipt["session_id"] == "session-1"
        assert receipt["gateway_session_id"] == "gateway-1"
        assert receipt["verified_room_vnum"] == 3001
        assert receipt["verified_room_title"] == "The Temple Of Midgaard"
        assert player.commands == ["save", "score", "look"]
        assert player.reconnects == 1
        assert player.control_state == "running"
        assert child_requests[0]["character"] == "Tester"
        assert journal.since("gateway-1", kind="reset_receipt")
    finally:
        journal.close()


async def test_relocation_pauses_and_retains_a_verified_receipt(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)
    child_requests: list[dict[str, object]] = []

    async def admin(
        payload: dict[str, object],
        _journal: Path,
        _progress: Path,
        _timeout: float,
    ) -> dict[str, object]:
        child_requests.append(payload)
        return {
            "ok": True,
            "applied": ("goto", "transfer"),
            "located": (3001, "The Temple Of Midgaard"),
            "exit_status": 0,
        }

    try:
        receipt = await ResetCoordinator(
            settings,
            session=lambda: player,
            admin_runner=admin,
        ).relocate(
            request(
                settings,
                action="relocate",
                baseline_id=None,
                baseline_version=None,
            )
        )

        assert receipt["ok"] is True
        assert receipt["action"] == "relocate"
        assert receipt["verified_room_vnum"] == 3001
        assert receipt["applied"] == ("goto", "transfer")
        assert child_requests[0]["action"] == "relocate"
        assert "baseline_id" not in child_requests[0]
        assert player.commands == ["look"]
        assert player.reconnects == 0
        assert player.control_state == "running"
        assert journal.since("gateway-1", kind="relocation_receipt")
    finally:
        journal.close()


async def test_reset_snapshots_then_retracts_learned_knowledge(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)
    knowledge = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    knowledge.assert_fact(
        "place:old",
        "title",
        "Old Room",
        layer="learned",
        confidence="high",
        evidence=EvidenceRef(
            "gateway-1",
            1,
            "wire-old",
            "rules-1",
            "room-frame",
            1.0,
        ),
    )

    async def admin(*_args) -> dict[str, object]:
        return {
            "ok": True,
            "applied": ("restore", "level", "transfer"),
            "located": (3001, "The Temple Of Midgaard"),
            "exit_status": 0,
        }

    try:
        receipt = await ResetCoordinator(
            settings,
            session=lambda: player,
            knowledge=knowledge,
            admin_runner=admin,
        ).reset(request(settings))

        assert receipt["ok"] is True
        assert receipt["knowledge_snapshot_id"]
        assert receipt["knowledge_snapshot_digest"]
        assert receipt["knowledge_retractions"] == 1
        assert knowledge.current_facts(layer="learned") == []
        assert knowledge.get_snapshot(receipt["knowledge_snapshot_id"]) is not None
        assert player.commands == ["save", "score", "look", "look"]
    finally:
        knowledge.close()
        journal.close()


async def test_restore_appends_verified_snapshot_through_selected_session(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)
    knowledge = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    knowledge.assert_fact(
        "place:old",
        "title",
        "Old Room",
        layer="learned",
        confidence="high",
        evidence=EvidenceRef(
            "gateway-1",
            1,
            "wire-old",
            "rules-1",
            "room-frame",
            1.0,
        ),
    )
    snapshot = knowledge.snapshot("before correction")
    knowledge.reset_learned(
        reason="correction",
        snapshot_id=snapshot.snapshot_id,
    )

    try:
        receipt = await ResetCoordinator(
            settings,
            session=lambda: player,
            knowledge=knowledge,
        ).restore_knowledge(
            request(
                settings,
                action="knowledge_restore",
                baseline_id=None,
                baseline_version=None,
                snapshot_id=snapshot.snapshot_id,
                reason="restore reviewed state",
            )
        )

        assert receipt["ok"] is True
        assert receipt["assertions"] == 1
        assert knowledge.current_facts(layer="learned")
        assert knowledge.recoveries()[-1].operation == "restore"
        assert journal.since("gateway-1", kind="knowledge_restore_receipt")
    finally:
        knowledge.close()
        journal.close()


async def test_restore_rejects_stale_sequence_and_invalid_snapshot(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)
    knowledge = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    journal.append("gateway-1", "observation", {"kind": "room"})
    coordinator = ResetCoordinator(
        settings,
        session=lambda: player,
        knowledge=knowledge,
    )

    try:
        with pytest.raises(ResetControlError, match="selected session advanced"):
            await coordinator.restore_knowledge(
                request(
                    settings,
                    action="knowledge_restore",
                    baseline_id=None,
                    baseline_version=None,
                    snapshot_id="missing",
                    reason="restore",
                    expected_sequence=0,
                )
            )
        with pytest.raises(
            ResetControlError,
            match="snapshot is missing or invalid",
        ):
            await coordinator.restore_knowledge(
                request(
                    settings,
                    action="knowledge_restore",
                    baseline_id=None,
                    baseline_version=None,
                    snapshot_id="missing",
                    reason="restore",
                    expected_sequence=journal.last_seq("gateway-1"),
                )
            )
    finally:
        knowledge.close()
        journal.close()


async def test_knowledge_failure_after_game_mutation_quarantines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)
    knowledge = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")

    async def admin(*_args) -> dict[str, object]:
        return {
            "ok": True,
            "applied": ("restore", "level", "transfer"),
            "located": (3001, "The Temple Of Midgaard"),
            "exit_status": 0,
        }

    def fail_reset(**_kwargs) -> int:
        raise RuntimeError("knowledge write failed")

    monkeypatch.setattr(knowledge, "reset_learned", fail_reset)
    try:
        receipt = await ResetCoordinator(
            settings,
            session=lambda: player,
            knowledge=knowledge,
            admin_runner=admin,
        ).reset(request(settings))

        assert receipt["ok"] is False
        assert receipt["error_type"] == "RuntimeError"
        assert receipt["knowledge_snapshot_id"]
        assert player.control_state == "quarantined"
    finally:
        knowledge.close()
        journal.close()


async def test_failure_before_mutation_resumes_selected_session(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)

    async def admin(*_args) -> dict[str, object]:
        return {
            "ok": False,
            "error": "admin unavailable",
            "error_type": "ConnectionError",
            "applied": (),
            "exit_status": 2,
        }

    try:
        receipt = await ResetCoordinator(
            settings,
            session=lambda: player,
            admin_runner=admin,
        ).reset(request(settings))

        assert receipt["ok"] is False
        assert receipt["applied"] == ()
        assert player.control_state == "running"
    finally:
        journal.close()


async def test_partial_mutation_quarantines_until_linked_retry(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)
    outcomes = [
        {
            "ok": False,
            "error": "transfer failed",
            "error_type": "AdminError",
            "applied": ("restore", "level"),
            "exit_status": 2,
        },
        {
            "ok": True,
            "applied": ("restore", "level", "transfer"),
            "located": (3001, "The Temple Of Midgaard"),
            "exit_status": 0,
        },
    ]

    async def admin(*_args) -> dict[str, object]:
        return outcomes.pop(0)

    try:
        coordinator = ResetCoordinator(
            settings,
            session=lambda: player,
            admin_runner=admin,
        )
        failed = await coordinator.reset(request(settings))
        assert player.control_state == "quarantined"

        retried = await coordinator.reset(request(
            settings,
            request_id="request-2",
            retry_of=failed["reset_id"],
            expected_sequence=journal.last_seq("gateway-1"),
        ))
        assert retried["ok"] is True
        assert retried["retry_of"] == failed["reset_id"]
        assert player.control_state == "running"
    finally:
        journal.close()


async def test_control_socket_authenticates_and_is_idempotent(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    journal = Journal(settings.journal)
    player = FakeSession(journal)
    calls = 0

    async def admin(*_args) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "ok": True,
            "applied": ("restore", "transfer"),
            "located": (3001, "The Temple Of Midgaard"),
            "exit_status": 0,
        }

    coordinator = ResetCoordinator(
        settings,
        session=lambda: player,
        admin_runner=admin,
    )
    server = ResetControlServer(
        settings.control_socket,
        settings.session_dir / "control.token",
        coordinator,
    )
    await server.start()
    try:
        payload = request(settings).model_dump_json() + "\n"
        for _ in range(2):
            reader, writer = await asyncio.open_unix_connection(
                settings.control_socket
            )
            writer.write(payload.encode())
            await writer.drain()
            response = json.loads(await reader.readline())
            writer.close()
            await writer.wait_closed()
            assert response["ok"] is True
        assert calls == 1
    finally:
        await server.close()
        journal.close()


def test_admin_child_environment_excludes_other_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    (tmp_path / ".env").write_text(
        "MUD_ADMIN_PASSWORD=admin-canary\n"
        "TESTER_PASSWORD=player-canary\n"
        "ANTHROPIC_API_KEY=provider-canary\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("MUD_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("TESTER_PASSWORD", "player-canary")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "provider-canary")

    environment = _admin_environment(settings)

    assert environment["MUD_ADMIN_PASSWORD"] == "admin-canary"
    assert "MUD_ADMIN_PASSWORD" not in os.environ
    assert "TESTER_PASSWORD" not in environment
    assert "ANTHROPIC_API_KEY" not in environment
    retained = "\n".join(
        path.read_text(errors="ignore")
        for path in settings.session_dir.rglob("*")
        if path.is_file()
    )
    assert "admin-canary" not in retained


async def test_command_boundary_times_out_and_quarantine_blocks_commands(
    tmp_path: Path,
) -> None:
    journal = Journal(tmp_path / "gateway.db")
    session = Session(
        journal,
        name="Tester",
        password="not-used",
        session_id="gateway-1",
    )
    try:
        await session._command_lock.acquire()
        with pytest.raises(SessionPaused, match="timed out"):
            async with session.pause(timeout=0.001):
                pass
        session._command_lock.release()

        session.quarantine("partial mutation")
        with pytest.raises(SessionQuarantined):
            await session.command("look")
    finally:
        journal.close()
