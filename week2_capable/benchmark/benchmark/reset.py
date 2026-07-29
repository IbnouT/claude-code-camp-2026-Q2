"""Typed reset through the gateway's private Unix-socket process."""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


class ResetError(RuntimeError):
    """A verified clean start could not be established."""


@dataclass(frozen=True)
class ResetResult:
    """The verified outcome returned by the admin process."""

    reset_id: str
    drift: tuple[str, ...]
    unread: tuple[str, ...]


def reset_once(
    *,
    socket_path: Path,
    journal_path: Path,
    environment: Mapping[str, str],
    command: Sequence[str] = ("boukensha-gateway-admin",),
    timeout: float = 30.0,
) -> ResetResult:
    """Start the admin process, request one reset, then close it before play."""
    arguments = [*command, "--socket", str(socket_path), "--journal", str(journal_path)]
    process = subprocess.Popen(
        arguments,
        env={**os.environ, **environment},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + timeout
    try:
        _wait_for_socket(process, socket_path, deadline)
        response = _request(socket_path, deadline)
        if response.get("ok") is not True:
            raise ResetError(str(response.get("error") or response))
        return ResetResult(
            reset_id=str(response.get("reset_id") or ""),
            drift=tuple(map(str, response.get("drift") or ())),
            unread=tuple(map(str, response.get("unread") or ())),
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_for_socket(
    process: subprocess.Popen[str], socket_path: Path, deadline: float
) -> None:
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _, error = process.communicate()
            raise ResetError(f"admin process exited before reset: {error.strip()}")
        if socket_path.exists():
            mode = socket_path.stat().st_mode
            if not stat.S_ISSOCK(mode):
                raise ResetError(f"admin path is not a socket: {socket_path}")
            if stat.S_IMODE(mode) != 0o600:
                raise ResetError("admin socket permissions are not 0600")
            return
        time.sleep(0.02)
    raise ResetError("timed out waiting for the admin socket")


def _request(socket_path: Path, deadline: float) -> dict[str, object]:
    remaining = max(0.1, deadline - time.monotonic())
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(remaining)
        client.connect(str(socket_path))
        client.sendall(b'{"operation":"reset"}\n')
        chunks: list[bytes] = []
        while not chunks or not chunks[-1].endswith(b"\n"):
            part = client.recv(65536)
            if not part:
                break
            chunks.append(part)
    try:
        value = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ResetError("admin process returned invalid JSON") from error
    if not isinstance(value, dict):
        raise ResetError("admin response must be an object")
    return value
