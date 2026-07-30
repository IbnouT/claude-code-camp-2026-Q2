"""Authenticated control socket for resetting one selected live session."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field

from .baseline import baseline
from .knowledge import KnowledgeStore, Snapshot
from .reset_client import ObservedState, parse_score, verify
from .session import Session
from .settings import GatewaySettings


class ControlRequest(BaseModel):
    """One idempotent request bound to the immutable runtime manifest."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: int = 1
    request_id: str = Field(min_length=1, max_length=200)
    action: str = "reset"
    token: str = Field(min_length=16, max_length=200)
    expected_state: str = "running"
    session_id: str
    gateway_session_id: str
    player_id: str
    character: str
    baseline_id: str
    baseline_version: int = Field(ge=1)
    expected_configuration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: str = Field(min_length=16, max_length=200)
    retry_of: str | None = None


class ResetControlError(RuntimeError):
    """A control request was invalid or could not complete safely."""


AdminRunner = Callable[
    [dict[str, Any], Path, Path, float],
    Awaitable[dict[str, Any]],
]


class ResetCoordinator:
    """Pause, mutate, verify, and resume or quarantine one live session."""

    def __init__(
        self,
        settings: GatewaySettings,
        *,
        session: Callable[[], Session | None],
        knowledge: KnowledgeStore | None = None,
        admin_runner: AdminRunner | None = None,
        pause_timeout: float | None = None,
        child_timeout: float | None = None,
    ) -> None:
        if settings.session_dir is None:
            raise ResetControlError("runtime session directory is required")
        self.settings = settings
        self._session = session
        self.knowledge = knowledge
        self._admin_runner = admin_runner or self._run_admin_child
        self.pause_timeout = (
            settings.reset_pause_timeout
            if pause_timeout is None
            else pause_timeout
        )
        self.child_timeout = (
            settings.reset_child_timeout
            if child_timeout is None
            else child_timeout
        )
        self.session_dir = settings.session_dir
        self.manifest = _load_object(self.session_dir / "session.json")
        self.state_path = self.session_dir / "control-state.json"
        self.progress_path = self.session_dir / "reset-progress.jsonl"
        self.admin_journal = self.session_dir / "admin.db"
        self._validate_manifest()
        self._project("running")

    async def reset(self, request: ControlRequest) -> dict[str, Any]:
        if request.protocol_version != 1 or request.action != "reset":
            raise ResetControlError("unsupported control request")
        self._validate_binding(request)
        selected = baseline(request.baseline_id, request.baseline_version)
        player = self._session()
        if player is None or not player.logged_in:
            raise ResetControlError("selected gateway session is not authenticated")

        retry = request.retry_of is not None
        if player.control_state == "quarantined":
            if not retry:
                raise ResetControlError(
                    "session is quarantined, retry_of is required"
                )
            player.allow_reset_retry()
        elif request.expected_state != player.control_state:
            raise ResetControlError(
                f"expected {request.expected_state!r}, found {player.control_state!r}"
            )

        reset_id = secrets.token_hex(16)
        knowledge_snapshot: Snapshot | None = None
        child_request = {
            "protocol_version": 1,
            "action": "reset",
            "request_id": request.request_id,
            "reset_id": reset_id,
            "session_id": request.session_id,
            "gateway_session_id": request.gateway_session_id,
            "player_id": request.player_id,
            "character": request.character,
            "baseline_id": selected.id,
            "baseline_version": selected.version,
            "baseline_digest": selected.digest,
            "configuration_digest": request.expected_configuration_digest,
            "nonce": request.nonce,
            "retry_of": request.retry_of,
        }
        self._project("pausing", reset_id=reset_id)
        applied: tuple[str, ...] = ()
        try:
            async with player.pause(timeout=self.pause_timeout):
                self._project("paused", reset_id=reset_id)
                if self.knowledge is not None:
                    knowledge_snapshot = self.knowledge.snapshot(
                        f"before reset {reset_id}"
                    )
                    if not self.knowledge.verify_snapshot(
                        knowledge_snapshot.snapshot_id
                    ):
                        raise ResetControlError(
                            "knowledge snapshot verification failed"
                        )
                child = await self._admin_runner(
                    child_request,
                    self.admin_journal,
                    self.progress_path,
                    self.child_timeout,
                )
                applied = tuple(map(str, child.get("applied") or ()))
                if child.get("ok") is not True:
                    return self._failed_receipt(
                        player,
                        request,
                        reset_id,
                        child,
                        applied,
                        knowledge_snapshot=knowledge_snapshot,
                    )
                state = await self._verify_mortal(player)
                located = _located(child.get("located"))
                drift = verify(
                    state,
                    located=located,
                    room=selected.room,
                    fields=selected.fields,
                )
                knowledge_retractions = 0
                if not drift and not state.unread and self.knowledge is not None:
                    knowledge_retractions = self.knowledge.reset_learned(
                        reason=f"{selected.id}@{selected.version}",
                        snapshot_id=knowledge_snapshot.snapshot_id,
                    )
                    player.journal.append(
                        player.id,
                        "observer_probe",
                        {
                            "command": "look",
                            "reason": "post_reset_knowledge_seed",
                            "reset_id": reset_id,
                        },
                    )
                    await player.reset_command("look")
                receipt = self._receipt(
                    request=request,
                    reset_id=reset_id,
                    ok=not drift and not state.unread,
                    state=state,
                    drift=drift,
                    applied=applied,
                    child=child,
                    knowledge_snapshot=knowledge_snapshot,
                    knowledge_retractions=knowledge_retractions,
                )
                if not receipt["ok"]:
                    player.quarantine("reset verification failed")
                    self._project(
                        "quarantined",
                        reset_id=reset_id,
                        reason="verification_failed",
                    )
                else:
                    self._project("running", reset_id=reset_id)
                player.journal.append(player.id, "reset_receipt", receipt)
                return receipt
        except asyncio.TimeoutError:
            applied = applied or _progress(self.progress_path, reset_id)
            child = {
                "ok": False,
                "error": "admin child timed out",
                "error_type": "TimeoutError",
                "applied": applied,
            }
            return self._failed_receipt(
                player,
                request,
                reset_id,
                child,
                applied,
                knowledge_snapshot=knowledge_snapshot,
            )
        except Exception as error:
            applied = applied or _progress(self.progress_path, reset_id)
            child = {
                "ok": False,
                "error": str(error),
                "error_type": type(error).__name__,
                "applied": applied,
            }
            return self._failed_receipt(
                player,
                request,
                reset_id,
                child,
                applied,
                knowledge_snapshot=knowledge_snapshot,
            )

    async def _verify_mortal(self, player: Session) -> ObservedState:
        await player.reset_command("save")
        await player.reconnect_for_reset()
        player.journal.append(
            player.id,
            "observer_probe",
            {"command": "score", "reason": "post_reset_player_state"},
        )
        score = await player.reset_command("score")
        await player.reset_command("look")
        facts = parse_score(score.text)
        snapshot = player.observations.snapshot()
        if snapshot.room is not None:
            facts["room_title"] = snapshot.room.title
            facts["exits"] = snapshot.room.exits
        return ObservedState(**facts)

    def _failed_receipt(
        self,
        player: Session,
        request: ControlRequest,
        reset_id: str,
        child: Mapping[str, Any],
        applied: Sequence[str],
        *,
        knowledge_snapshot: Snapshot | None,
    ) -> dict[str, Any]:
        mutated = bool(applied)
        if mutated:
            player.quarantine("admin reset failed after mutation")
            self._project(
                "quarantined",
                reset_id=reset_id,
                reason="partial_mutation",
            )
        else:
            self._project(
                "running",
                reset_id=reset_id,
                reason="failed_before_mutation",
            )
        receipt = self._receipt(
            request=request,
            reset_id=reset_id,
            ok=False,
            state=None,
            drift={},
            applied=tuple(applied),
            child=child,
            knowledge_snapshot=knowledge_snapshot,
            knowledge_retractions=0,
        )
        player.journal.append(player.id, "reset_receipt", receipt)
        return receipt

    def _receipt(
        self,
        *,
        request: ControlRequest,
        reset_id: str,
        ok: bool,
        state: ObservedState | None,
        drift: Mapping[str, Any],
        applied: Sequence[str],
        child: Mapping[str, Any],
        knowledge_snapshot: Snapshot | None,
        knowledge_retractions: int,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "request_id": request.request_id,
            "reset_id": reset_id,
            "retry_of": request.retry_of,
            "session_id": request.session_id,
            "gateway_session_id": request.gateway_session_id,
            "player_id": request.player_id,
            "character": request.character,
            "baseline_id": request.baseline_id,
            "baseline_version": request.baseline_version,
            "configuration_digest": request.expected_configuration_digest,
            "state": None if state is None else asdict(state),
            "drift": dict(drift),
            "unread": () if state is None else state.unread,
            "applied": tuple(applied),
            "child_exit_status": child.get("exit_status"),
            "knowledge_snapshot_id": (
                None if knowledge_snapshot is None else knowledge_snapshot.snapshot_id
            ),
            "knowledge_snapshot_digest": (
                None if knowledge_snapshot is None else knowledge_snapshot.digest
            ),
            "knowledge_retractions": knowledge_retractions,
            "error": child.get("error"),
            "error_type": child.get("error_type"),
        }

    async def _run_admin_child(
        self,
        request: dict[str, Any],
        journal_path: Path,
        progress_path: Path,
        timeout: float,
    ) -> dict[str, Any]:
        environment = _admin_environment(self.settings)
        process = await asyncio.create_subprocess_exec(
            "boukensha-gateway-admin",
            "--journal",
            str(journal_path),
            "--progress",
            str(progress_path),
            "--host",
            self.settings.host,
            "--port",
            str(self.settings.port),
            "--admin",
            self.settings.admin_character,
            "--password-env",
            self.settings.admin_password_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        encoded = (json.dumps(request, sort_keys=True) + "\n").encode()
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(encoded),
                timeout=timeout,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        response = _last_object(stdout.decode(errors="replace"))
        response["exit_status"] = process.returncode
        if process.returncode != 0 and "error" not in response:
            response["error"] = _sanitized_stderr(stderr)
        return response

    def _validate_manifest(self) -> None:
        expected = {
            "session_id": self.settings.session_id,
            "gateway_session_id": self.settings.gateway_session_id,
            "player_id": self.settings.player_profile,
            "character": self.settings.character,
        }
        for name, value in expected.items():
            if value is None or self.manifest.get(name) != value:
                raise ResetControlError(f"runtime manifest mismatch for {name}")

    def _validate_binding(self, request: ControlRequest) -> None:
        expected = {
            "session_id": request.session_id,
            "gateway_session_id": request.gateway_session_id,
            "player_id": request.player_id,
            "character": request.character,
            "configuration_digest": request.expected_configuration_digest,
        }
        for name, value in expected.items():
            if self.manifest.get(name) != value:
                raise ResetControlError(f"reset target mismatch for {name}")

    def _project(self, state: str, **detail: Any) -> None:
        value = {"schema_version": 1, "state": state, **detail}
        temporary = self.state_path.with_suffix(".tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.state_path)


class ResetControlServer:
    """One local-owner socket with token authentication and idempotent replies."""

    def __init__(
        self,
        socket_path: Path,
        token_path: Path,
        coordinator: ResetCoordinator,
    ) -> None:
        self.socket_path = socket_path
        self.token = token_path.read_text(encoding="utf-8").strip()
        self.coordinator = coordinator
        self._listener: asyncio.AbstractServer | None = None
        self._responses: dict[str, dict[str, Any]] = {}
        self._request_lock = asyncio.Lock()

    async def start(self) -> None:
        self.socket_path.unlink(missing_ok=True)
        self._listener = await asyncio.start_unix_server(
            self._handle,
            path=self.socket_path,
        )
        os.chmod(self.socket_path, 0o600)

    async def close(self) -> None:
        if self._listener is not None:
            self._listener.close()
            await self._listener.wait_closed()
        self.socket_path.unlink(missing_ok=True)

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request = ControlRequest.model_validate_json(await reader.readline())
            if not hmac.compare_digest(request.token, self.token):
                raise ResetControlError("control authentication failed")
            async with self._request_lock:
                response = self._responses.get(request.request_id)
                if response is None:
                    response = await self.coordinator.reset(request)
                    self._responses[request.request_id] = response
        except Exception as error:
            response = {
                "ok": False,
                "error": str(error),
                "error_type": type(error).__name__,
            }
        writer.write((json.dumps(response, sort_keys=True) + "\n").encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()


def _admin_environment(settings: GatewaySettings) -> dict[str, str]:
    secret = os.environ.get(settings.admin_password_env)
    if not secret:
        configured_secret_file = os.environ.get("BOUKENSHA_ADMIN_SECRET_FILE")
        secret_file = (
            Path(configured_secret_file).expanduser().resolve()
            if configured_secret_file
            else settings.config_dir / ".env"
        )
        secret = dotenv_values(
            secret_file
        ).get(settings.admin_password_env)
    if not secret:
        raise ResetControlError(
            f"{settings.admin_password_env} is required for authenticated reset"
        )
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in {
            "HOME", "LANG", "LC_ALL", "LC_CTYPE", "PATH", "SHELL",
            "TMPDIR", "TZ",
        } or name.startswith("LC_")
    }
    environment[settings.admin_password_env] = str(secret)
    return environment


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ResetControlError(f"{path} must contain a JSON object")
    return value


def _last_object(text: str) -> dict[str, Any]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return {"ok": False, "error": "admin child returned no receipt"}
    value = json.loads(lines[-1])
    if not isinstance(value, dict):
        raise ResetControlError("admin child receipt must be an object")
    return value


def _sanitized_stderr(value: bytes) -> str:
    text = value.decode(errors="replace").strip()
    return "admin child failed" if not text else text[:300]


def _located(value: Any) -> tuple[int, str] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return int(value[0]), str(value[1])
    return None


def _progress(path: Path, reset_id: str) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    operations: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("reset_id") == reset_id:
            operation = row.get("operation")
            if isinstance(operation, str):
                operations.append(operation)
    return tuple(operations)
