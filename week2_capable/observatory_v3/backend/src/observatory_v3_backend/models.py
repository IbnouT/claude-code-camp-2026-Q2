"""Typed repository records before public API projection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """One launcher-owned session row with validated source identity."""

    session_id: str
    player_id: str
    character: str
    agent_id: str
    gateway_session_id: str
    experiment_id: str | None
    run_id: str | None
    session_dir: Path
    manifest_path: Path
    control_socket: Path
    state: str
    pid: int | None
    created_at: str
    updated_at: str
    ended_at: str | None
    exit_code: int | None
    stop_mode: str | None
    capture_status: str
    legacy: bool

    @property
    def live(self) -> bool:
        """Return whether the launcher considers this session active."""
        return self.state in {
            "starting",
            "running",
            "draining",
            "quarantined",
        }

    def __str__(self) -> str:
        return (
            f"<SessionRecord session_id={self.session_id} "
            f"player_id={self.player_id} state={self.state}>"
        )


@dataclass(frozen=True, slots=True)
class GatewayEventRecord:
    """One committed gateway event."""

    sequence: int
    session_id: str
    at: float
    monotonic: float
    kind: str
    trace_id: str | None
    payload: dict[str, Any]

    def __str__(self) -> str:
        return (
            f"<GatewayEventRecord sequence={self.sequence} "
            f"session_id={self.session_id} kind={self.kind}>"
        )


@dataclass(frozen=True, slots=True)
class AgentPage:
    """A bounded page from one append-only agent JSONL source."""

    records: tuple[dict[str, Any], ...]
    next_offset: int
    next_line: int
    incomplete_tail: bool

    def __str__(self) -> str:
        return (
            f"<AgentPage records={len(self.records)} "
            f"next_offset={self.next_offset} "
            f"next_line={self.next_line} "
            f"incomplete_tail={self.incomplete_tail}>"
        )


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    """One launcher lifecycle transition."""

    sequence: int
    session_id: str
    at: str
    state: str
    detail: dict[str, Any]

    def __str__(self) -> str:
        return (
            f"<LifecycleRecord sequence={self.sequence} "
            f"session_id={self.session_id} state={self.state}>"
        )


@dataclass(frozen=True, slots=True)
class ControlStatus:
    """Public-safe effective control state without token contents."""

    state: str | None
    available: bool

    def __str__(self) -> str:
        return f"<ControlStatus state={self.state} available={self.available}>"
