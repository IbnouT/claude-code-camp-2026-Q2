"""Hermetic multi-player process and evidence isolation gates."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from boukensha.runtime import (
    CharacterAlreadyRunning,
    RuntimeIdentity,
    RuntimeSession,
    SessionRegistry,
    import_legacy_session,
)

WORKER = Path(__file__).with_name("runtime_worker.py")


def _config(root: Path) -> Path:
    config = root / ".boukensha"
    config.mkdir()
    (config / "settings.yaml").write_text(
        "gateway:\n"
        "  connection:\n"
        "    player_profile: alpha\n"
        "  players:\n"
        "    alpha:\n"
        "      character: Alpha\n"
        "      password_env: PLAYER_ALPHA\n"
        "    beta:\n"
        "      character: Beta\n"
        "      password_env: PLAYER_BETA\n",
        encoding="utf-8",
    )
    return config


def _worker(
    config: Path,
    player: str,
    character: str,
    cost: float,
    tokens: int,
) -> tuple[subprocess.Popen[str], dict]:
    process = subprocess.Popen(
        [
            sys.executable,
            str(WORKER),
            str(config),
            player,
            character,
            str(cost),
            str(tokens),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "ADMIN_CANARY": "must-not-pass",
            "PLAYER_OTHER": "must-not-pass",
        },
    )
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line, process.stderr.read() if process.stderr else ""
    return process, json.loads(line)


def _stop(process: subprocess.Popen[str]) -> None:
    assert process.stdin is not None
    process.stdin.write("\n")
    process.stdin.flush()
    assert process.wait(timeout=5) == 0


def test_runtime_manifest_is_immutable_and_protected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        runtime = RuntimeSession.create(
            config,
            player_id="alpha",
            character="Alpha",
        )
        try:
            manifest = json.loads(runtime.paths.manifest.read_text())
            assert manifest["session_id"] == runtime.identity.session_id
            assert manifest["gateway_session_id"] == runtime.identity.gateway_session_id
            assert manifest["player_id"] == "alpha"
            assert manifest["layout_version"] == 1
            assert stat.S_IMODE(runtime.paths.session_dir.stat().st_mode) == 0o700
            assert stat.S_IMODE(runtime.paths.control_token.stat().st_mode) == 0o600
            assert len(str(runtime.paths.control_socket)) < 104
            assert runtime.paths.control_socket.parent == Path(tempfile.gettempdir())
        finally:
            runtime.close()


def test_same_character_is_rejected_with_a_typed_error() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        first = RuntimeSession.create(
            config,
            player_id="alpha",
            character="Shared",
        )
        try:
            with pytest.raises(CharacterAlreadyRunning):
                RuntimeSession.create(
                    config,
                    player_id="beta",
                    character="Shared",
                )
        finally:
            first.close()


def test_restricted_child_environment_keeps_only_selected_secrets() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        runtime = RuntimeSession.create(
            config,
            player_id="alpha",
            character="Alpha",
        )
        try:
            environment = runtime.child_environment(
                parent={
                    "PATH": "/bin",
                    "ADMIN_CANARY": "admin",
                    "PLAYER_BETA": "beta",
                },
                secrets={"PLAYER_ALPHA": "alpha"},
            )
            assert environment["PATH"] == "/bin"
            assert environment["PLAYER_ALPHA"] == "alpha"
            assert "ADMIN_CANARY" not in environment
            assert "PLAYER_BETA" not in environment
            assert environment["BOUKENSHA_PLAYER_ID"] == "alpha"
        finally:
            runtime.close()


def test_two_agent_processes_isolate_evidence_cost_tokens_and_stop() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        alpha, alpha_info = _worker(config, "alpha", "Alpha", 0.11, 11)
        beta, beta_info = _worker(config, "beta", "Beta", 0.22, 22)
        try:
            assert alpha_info["session_id"] != beta_info["session_id"]
            assert alpha_info["session_dir"] != beta_info["session_dir"]
            assert alpha_info["secret_names"] == ["PLAYER_ALPHA"]
            assert beta_info["secret_names"] == ["PLAYER_BETA"]

            for info, expected_cost, expected_tokens in (
                (alpha_info, 0.11, 11),
                (beta_info, 0.22, 22),
            ):
                session_dir = Path(info["session_dir"])
                events = [
                    json.loads(line)
                    for line in (session_dir / "agent.jsonl").read_text().splitlines()
                ]
                assert all(event["player_id"] == info["player_id"] for event in events)
                assert all(event["session_id"] == info["session_id"] for event in events)
                turn_end = next(event for event in events if event["phase"] == "turn_end")
                assert turn_end["cost_usd"] == expected_cost
                assert turn_end["tokens"] == expected_tokens
                database = sqlite3.connect(session_dir / "gateway.db")
                owner = database.execute(
                    "SELECT player_id, session_id FROM ownership"
                ).fetchone()
                database.close()
                assert owner == (info["player_id"], info["session_id"])

            _stop(alpha)
            assert beta.poll() is None
            registry = SessionRegistry(config)
            try:
                states = {
                    row["player_id"]: row["state"]
                    for row in registry.sessions()
                }
            finally:
                registry.close()
            assert states["alpha"] == "stopped"
            assert states["beta"] == "running"
        finally:
            if alpha.poll() is None:
                _stop(alpha)
            if beta.poll() is None:
                _stop(beta)


def test_runtime_ids_are_uuid4() -> None:
    identity = RuntimeIdentity.create(player_id="alpha", character="Alpha")
    import uuid

    assert uuid.UUID(identity.agent_id).version == 4
    assert uuid.UUID(identity.session_id).version == 4
    assert uuid.UUID(identity.gateway_session_id).version == 4


def test_legacy_import_is_idempotent_and_keeps_the_original() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        config = _config(root)
        source = root / "old-session.jsonl"
        source.write_text('{"phase":"turn_end","session_id":"old"}\n')

        first = import_legacy_session(
            config,
            source,
            player_id="alpha",
            character="Alpha",
        )
        second = import_legacy_session(
            config,
            source,
            player_id="alpha",
            character="Alpha",
        )

        assert first == second
        assert source.read_text() == '{"phase":"turn_end","session_id":"old"}\n'
        session = config / "profiles" / "alpha" / "sessions" / first.session_id
        manifest = json.loads((session / "session.json").read_text())
        assert manifest["legacy"] is True
        assert "gateway_journal" in manifest["capture_gaps"]
        assert (session / "agent.jsonl").read_text() == source.read_text()
        registry = SessionRegistry(config)
        try:
            rows = registry.sessions(player_id="alpha")
        finally:
            registry.close()
        assert len(rows) == 1
        assert rows[0]["legacy"] == 1


def test_crash_recovery_reconciles_registry_after_kernel_releases_lock() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        crashed, crashed_info = _worker(config, "alpha", "Alpha", 0.1, 10)
        crashed.kill()
        assert crashed.wait(timeout=5) < 0

        replacement = RuntimeSession.create(
            config,
            player_id="alpha",
            character="Alpha",
        )
        try:
            rows = replacement.registry.sessions(player_id="alpha")
            states = {row["session_id"]: row["state"] for row in rows}
            assert states[crashed_info["session_id"]] == "crashed"
            assert states[replacement.identity.session_id] == "starting"
        finally:
            replacement.close()
