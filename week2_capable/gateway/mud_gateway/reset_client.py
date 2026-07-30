"""Reset one already authenticated gateway session through its control socket."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sqlite3
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .baseline import DEFAULT_FIELDS, LEVEL1_TEMPLE, TEMPLE
from .settings import GatewaySettings

SCORE_PATTERNS = {
    "hit": re.compile(r"You have (\d+)\((\d+)\) hit"),
    "mana": re.compile(r"(\d+)\((\d+)\) mana"),
    "move": re.compile(r"(\d+)\((\d+)\) movement"),
    "exp": re.compile(r"You have (\d+) exp,"),
    "gold": re.compile(r"(\d+) gold coins"),
    "level": re.compile(r"\(level (\d+)\)"),
    "align": re.compile(r"alignment is (-?\d+)"),
}
POSITION = re.compile(r"You are (standing|sitting|resting|sleeping)\.")
HUNGRY = re.compile(r"You are hungry\.")
THIRSTY = re.compile(r"You are thirsty\.")


class ResetClientError(RuntimeError):
    """The selected authenticated session could not be reset and verified."""


@dataclass(frozen=True)
class ObservedState:
    """State read back through the selected mortal connection."""

    level: int | None = None
    hit: tuple[int, int] | None = None
    mana: tuple[int, int] | None = None
    move: tuple[int, int] | None = None
    gold: int | None = None
    exp: int | None = None
    align: int | None = None
    position: str | None = None
    hungry: bool | None = None
    thirsty: bool | None = None
    room_title: str | None = None
    exits: tuple[str, ...] | None = None

    @property
    def unread(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in self.__dataclass_fields__
            if getattr(self, name) is None
        )


def parse_score(text: str) -> dict[str, object]:
    """Parse complete character state from the mortal ``score`` response."""
    found: dict[str, object] = {}
    for name, pattern in SCORE_PATTERNS.items():
        match = pattern.search(text)
        if match:
            found[name] = (
                (int(match.group(1)), int(match.group(2)))
                if name in {"hit", "mana", "move"}
                else int(match.group(1))
            )
    posture = POSITION.search(text)
    if posture:
        found["position"] = posture.group(1)
    found["hungry"] = bool(HUNGRY.search(text))
    found["thirsty"] = bool(THIRSTY.search(text))
    return found


def verify(
    state: ObservedState,
    *,
    located: tuple[int, str] | None,
    room: int = TEMPLE,
    fields: Mapping[str, int] | None = None,
) -> dict[str, tuple[object, object]]:
    """Compare mortal evidence and admin location with one exact baseline."""
    expected_fields = DEFAULT_FIELDS if fields is None else fields
    expected: dict[str, object] = {
        "level": expected_fields.get("level"),
        "gold": expected_fields.get("gold"),
        "exp": expected_fields.get("exp"),
        "align": expected_fields.get("align"),
        "hungry": not bool(expected_fields.get("hunger", 0)),
        "thirsty": not bool(expected_fields.get("thirst", 0)),
    }
    drift = {
        name: (wanted, getattr(state, name))
        for name, wanted in expected.items()
        if wanted is not None and getattr(state, name) != wanted
    }
    for name in ("hit", "mana", "move"):
        pair = getattr(state, name)
        if pair is not None and pair[0] != pair[1]:
            drift[name] = ("full", pair)
    if located is None:
        drift["room"] = (room, None)
    else:
        actual_room, title = located
        if actual_room != room:
            drift["room"] = (room, actual_room)
        if (
            state.room_title is not None
            and state.room_title.casefold() != title.casefold()
        ):
            drift["room_title"] = (title, state.room_title)
    return drift


def request_reset(
    session_dir: Path,
    *,
    retry_of: str | None = None,
    expected_sequence: int | None = None,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Request a reset using only the selected session's immutable authority."""
    return _request_control(
        session_dir,
        action="reset",
        timeout=timeout,
        retry_of=retry_of,
        expected_sequence=expected_sequence,
    )


def request_knowledge_restore(
    session_dir: Path,
    *,
    snapshot_id: str,
    reason: str,
    expected_sequence: int,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Restore one verified snapshot through its authenticated live session."""

    return _request_control(
        session_dir,
        action="knowledge_restore",
        timeout=timeout,
        snapshot_id=snapshot_id,
        reason=reason,
        expected_sequence=expected_sequence,
    )


def _request_control(
    session_dir: Path,
    *,
    action: str,
    timeout: float,
    retry_of: str | None = None,
    snapshot_id: str | None = None,
    reason: str | None = None,
    expected_sequence: int | None = None,
) -> dict[str, Any]:
    directory = session_dir.expanduser().resolve()
    manifest = _object(directory / "session.json")
    token = (directory / "control.token").read_text(encoding="utf-8").strip()
    socket_path = Path(str(manifest["control_socket"]))
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
        "baseline_id": LEVEL1_TEMPLE.id,
        "baseline_version": LEVEL1_TEMPLE.version,
        "expected_configuration_digest": manifest["configuration_digest"],
        "expected_sequence": (
            _latest_sequence(directory / "gateway.db", manifest["gateway_session_id"])
            if expected_sequence is None
            else expected_sequence
        ),
        "nonce": secrets.token_hex(16),
        "retry_of": retry_of,
        "snapshot_id": snapshot_id,
        "reason": reason,
    }
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
        raise ResetClientError("control endpoint returned invalid JSON") from error
    if not isinstance(response, dict):
        raise ResetClientError("control receipt must be an object")
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
        raise ResetClientError(
            "selected session sequence is unavailable"
        ) from error
    return int(row[0]) if row is not None else 0


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ResetClientError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    settings = GatewaySettings.load()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-dir",
        type=Path,
        required=True,
        help="selected live runtime session directory",
    )
    parser.add_argument(
        "--retry-of",
        help="failed reset id when retrying a quarantined session",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=settings.reset_client_timeout,
        help="control response timeout in seconds",
    )
    arguments = parser.parse_args(argv)
    try:
        receipt = request_reset(
            arguments.session_dir,
            retry_of=arguments.retry_of,
            timeout=arguments.timeout,
        )
    except Exception as error:
        receipt = {
            "ok": False,
            "error": str(error),
            "error_type": type(error).__name__,
        }
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt.get("ok") is True else 2


if __name__ == "__main__":
    sys.exit(main())
