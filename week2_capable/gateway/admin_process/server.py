"""One-shot privileged reset child with one typed stdin request."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mud_gateway.admin import AdminSession
from mud_gateway.baseline import baseline
from mud_gateway.journal import Journal

from .reset import ResetMutationError, ResetPlan


class ResetRequest(BaseModel):
    """Immutable reset authority supplied by the paused gateway."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: int = 1
    action: str = "reset"
    request_id: str = Field(min_length=1, max_length=200)
    reset_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    gateway_session_id: str = Field(min_length=1, max_length=200)
    player_id: str = Field(min_length=1, max_length=200)
    character: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    baseline_id: str
    baseline_version: int = Field(ge=1)
    baseline_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: str = Field(min_length=16, max_length=200)
    retry_of: str | None = None


class ProgressWriter:
    """Durable mutation evidence that survives a killed child."""

    def __init__(self, path: Path, reset_id: str) -> None:
        self.path = path
        self.reset_id = reset_id
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def append(self, operation: str) -> None:
        descriptor = os.open(
            self.path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "reset_id": self.reset_id,
                "operation": operation,
            }, sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())


async def execute(
    request: ResetRequest,
    *,
    admin_name: str,
    admin_password: str,
    journal_path: Path,
    progress_path: Path,
    host: str,
    port: int,
) -> dict[str, Any]:
    """Apply exactly one validated baseline and return one final receipt."""
    if request.protocol_version != 1 or request.action != "reset":
        raise ValueError("unsupported reset protocol request")
    selected = baseline(request.baseline_id, request.baseline_version)
    if selected.digest != request.baseline_digest:
        raise ValueError("reset baseline digest mismatch")

    journal = Journal(journal_path)
    admin = AdminSession(
        journal,
        name=admin_name,
        password=admin_password,
        host=host,
        port=port,
    )
    progress = ProgressWriter(progress_path, request.reset_id)
    try:
        await admin.open()
        outcome = await ResetPlan(
            selected.fields,
            room=selected.room,
            reset_id=request.reset_id,
            on_progress=progress.append,
        ).apply(
            admin,
            request.character,
            session_id=request.session_id,
        )
        return {
            "ok": outcome.ok,
            "request_id": request.request_id,
            "reset_id": outcome.reset_id,
            "session_id": outcome.session_id,
            "gateway_session_id": request.gateway_session_id,
            "player_id": request.player_id,
            "character": outcome.player,
            "baseline_id": selected.id,
            "baseline_version": selected.version,
            "baseline_digest": selected.digest,
            "located": outcome.located,
            "drift": outcome.drift,
            "applied": outcome.applied,
            "retry_of": request.retry_of,
        }
    except ResetMutationError as error:
        return {
            "ok": False,
            "request_id": request.request_id,
            "reset_id": error.reset_id,
            "error": str(error),
            "error_type": type(error.__cause__).__name__,
            "applied": error.applied,
            "retry_of": request.retry_of,
        }
    except Exception as error:
        return {
            "ok": False,
            "request_id": request.request_id,
            "reset_id": request.reset_id,
            "error": str(error),
            "error_type": type(error).__name__,
            "applied": (),
            "retry_of": request.retry_of,
        }
    finally:
        try:
            await admin.close()
        finally:
            journal.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4000)
    parser.add_argument("--admin", default="admin")
    parser.add_argument("--password-env", default="MUD_ADMIN_PASSWORD")
    arguments = parser.parse_args(argv)
    admin_password = os.environ.get(arguments.password_env)
    if not admin_password:
        parser.error(
            f"{arguments.password_env} is required in the process environment"
        )
    try:
        request = ResetRequest.model_validate_json(sys.stdin.readline())
        result = asyncio.run(
            execute(
                request,
                admin_name=arguments.admin,
                admin_password=admin_password,
                journal_path=arguments.journal,
                progress_path=arguments.progress,
                host=arguments.host,
                port=arguments.port,
            )
        )
    except Exception as error:
        result = {
            "ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
            "applied": (),
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
