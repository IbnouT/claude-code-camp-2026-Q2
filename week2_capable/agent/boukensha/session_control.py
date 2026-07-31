"""Internal preflight control for one launcher-owned gateway session."""

from __future__ import annotations

import json
import secrets
import socket
import sqlite3
from pathlib import Path
from typing import Any


class SessionControlError(RuntimeError):
    """A launcher-requested session control operation failed."""


def reset_selected_session(
    session_dir: Path,
    baseline: str,
    *,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Reset the already authenticated gateway selected by the launcher."""
    baseline_id, baseline_version = _baseline(baseline)
    return _request_selected_session(
        session_dir,
        action="reset",
        timeout=timeout,
        baseline_id=baseline_id,
        baseline_version=baseline_version,
    )


def relocate_selected_session(
    session_dir: Path,
    *,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Relocate the authenticated player without changing stats or items."""
    return _request_selected_session(
        session_dir,
        action="relocate",
        timeout=timeout,
    )


def _request_selected_session(
    session_dir: Path,
    *,
    action: str,
    timeout: float,
    baseline_id: str | None = None,
    baseline_version: int | None = None,
) -> dict[str, Any]:
    manifest = _object(session_dir / "session.json")
    token = (session_dir / "control.token").read_text(encoding="utf-8").strip()
    request = {
        "protocol_version": 1,
        "request_id": secrets.token_hex(16),
        "action": action,
        "token": token,
        "expected_state": "running",
        "session_id": manifest["session_id"],
        "gateway_session_id": manifest["gateway_session_id"],
        "player_id": manifest["player_id"],
        "character": manifest["character"],
        "baseline_id": baseline_id,
        "baseline_version": baseline_version,
        "expected_configuration_digest": manifest["configuration_digest"],
        "expected_sequence": _latest_sequence(
            session_dir / "gateway.db",
            manifest["gateway_session_id"],
        ),
        "nonce": secrets.token_hex(16),
    }
    socket_path = Path(str(manifest["control_socket"]))
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall((json.dumps(request, sort_keys=True) + "\n").encode())
        chunks: list[bytes] = []
        while not chunks or not chunks[-1].endswith(b"\n"):
            part = client.recv(65536)
            if not part:
                break
            chunks.append(part)
    try:
        response = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SessionControlError("gateway returned an invalid control receipt") from error
    if not isinstance(response, dict):
        raise SessionControlError("gateway control receipt must be an object")
    if response.get("ok") is not True:
        raise SessionControlError(
            str(response.get("error") or "gateway control did not verify")
        )
    return response


def _latest_sequence(path: Path, session_id: object) -> int:
    try:
        with sqlite3.connect(
            f"file:{path.resolve()}?mode=ro",
            uri=True,
        ) as database:
            row = database.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM events WHERE session = ?",
                (str(session_id),),
            ).fetchone()
    except sqlite3.Error as error:
        raise SessionControlError(
            "selected session sequence is unavailable"
        ) from error
    return int(row[0]) if row is not None else 0


def _baseline(value: str) -> tuple[str, int]:
    name, separator, version = value.partition("@")
    if not separator or not name or not version.isdigit() or int(version) < 1:
        raise SessionControlError(
            "reset baseline must use the form name@positive-version"
        )
    return name, int(version)


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SessionControlError(f"{path} must contain a JSON object")
    return value
