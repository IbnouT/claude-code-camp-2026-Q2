"""Internal durable lifecycle command models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CommandAction = Literal["start", "guide", "revise", "pause", "resume", "stop"]
CommandState = Literal["queued", "running", "succeeded", "failed"]
ResetMode = Literal["none", "temple", "baseline"]


@dataclass(frozen=True, slots=True)
class CommandSubmission:
    """One validated mutation before durable identity is assigned."""

    idempotency_key: str
    action: CommandAction
    actor: str
    player_id: str
    session_id: str | None
    expected_cursor: str | None
    instruction: str | None
    force: bool = False
    reset: ResetMode = "none"


@dataclass(frozen=True, slots=True)
class Command:
    """One public-safe durable lifecycle command."""

    id: str
    idempotency_key: str
    action: CommandAction
    actor: str
    player_id: str
    session_id: str | None
    expected_cursor: str | None
    instruction: str | None
    force: bool
    state: CommandState
    submitted_at: str
    started_at: str | None
    finished_at: str | None
    result_code: str | None
    result_detail: str | None
    result_session_id: str | None
    reset: ResetMode = "none"

    @property
    def terminal(self) -> bool:
        return self.state in {"succeeded", "failed"}
