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
    REGISTRY_SCHEMA_VERSION,
    RuntimeIdentity,
    RuntimeIdentityError,
    RuntimeSession,
    SessionRegistry,
    import_legacy_session,
)
from boukensha.runtime_cli import _with_control_state

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


def test_registry_owner_versions_a_new_schema() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        registry = SessionRegistry(config)
        registry.close()

        with sqlite3.connect(config / "registry.db") as database:
            version = int(database.execute("PRAGMA user_version").fetchone()[0])

        assert version == REGISTRY_SCHEMA_VERSION


def test_registry_owner_rejects_unknown_schema_without_mutation() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        source = config / "registry.db"
        with sqlite3.connect(source) as database:
            database.execute("PRAGMA user_version=99")
            database.execute("CREATE TABLE canary (value TEXT)")
        before = source.read_bytes()

        with pytest.raises(RuntimeIdentityError, match="version 99"):
            SessionRegistry(config)

        assert source.read_bytes() == before


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
            row = {
                "state": "running",
                "session_dir": str(runtime.paths.session_dir),
            }
            discovered = _with_control_state(row)
            assert discovered["knowledge_available"] is False
            assert discovered["knowledge_source"] == "player_knowledge_db"
        finally:
            runtime.close()


def test_discovery_reads_per_player_knowledge_cursor_without_writing() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        runtime = RuntimeSession.create(
            config,
            player_id="alpha",
            character="Alpha",
        )
        try:
            knowledge = config / "profiles" / "alpha" / "knowledge.db"
            connection = sqlite3.connect(knowledge)
            connection.executescript(
                "CREATE TABLE changes (change_seq INTEGER);"
                "CREATE TABLE snapshots (generation INTEGER);"
                "INSERT INTO changes VALUES (9);"
                "INSERT INTO snapshots VALUES (2);"
            )
            connection.close()
            discovered = _with_control_state({
                "state": "running",
                "session_dir": str(runtime.paths.session_dir),
            })
            assert discovered["knowledge_available"] is True
            assert discovered["knowledge_change_seq"] == 9
            assert discovered["knowledge_snapshot_generation"] == 2
            assert discovered["knowledge_source"] == "player_knowledge_db"
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


def test_experiment_run_identity_maps_to_one_launcher_session() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        config = _config(Path(temporary))
        first = RuntimeSession.create(
            config,
            player_id="alpha",
            character="Alpha",
            experiment_id="experiment-1",
            run_id="sample-1",
        )
        first.close()

        with pytest.raises(RuntimeIdentityError, match="already registered"):
            RuntimeSession.create(
                config,
                player_id="beta",
                character="Beta",
                experiment_id="experiment-1",
                run_id="sample-1",
            )


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
                knowledge = sqlite3.connect(info["knowledge_path"])
                assertion = knowledge.execute(
                    "SELECT f.subject, a.value_json, a.session_id "
                    "FROM facts AS f JOIN assertions AS a "
                    "ON a.assertion_id = f.current_assertion_id"
                ).fetchone()
                change_seq = knowledge.execute(
                    "SELECT MAX(change_seq) FROM changes"
                ).fetchone()[0]
                knowledge.close()
                assert assertion == (
                    f"player:{info['player_id']}",
                    json.dumps(
                        f"{info['player_id']}-knowledge-canary",
                        separators=(",", ":"),
                    ),
                    info["gateway_session_id"],
                )
                assert change_seq == 1

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


def test_discovery_labels_process_and_gateway_control_state_sources(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "control-state.json").write_text(
        '{"schema_version":1,"state":"quarantined"}\n',
        encoding="utf-8",
    )

    row = _with_control_state({
        "session_id": "session-1",
        "session_dir": str(session_dir),
        "state": "running",
    })

    assert row["process_state"] == "running"
    assert row["process_state_source"] == "launcher_registry"
    assert row["control_state"] == "quarantined"
    assert row["control_state_source"] == "gateway_projection"
