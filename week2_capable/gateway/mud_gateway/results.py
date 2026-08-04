"""Typed MCP result envelopes for gateway commands."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CommandObservation(BaseModel):
    type: Literal["observation"] = "observation"
    tool: str
    capability: str
    family: str
    command: str | None
    text: str
    complete: bool
    sequence: int
    trace_id: str


class CommandFailure(BaseModel):
    type: Literal["error"] = "error"
    tool: str
    capability: str | None = None
    family: str | None = None
    code: Literal[
        "permission_denied",
        "capability_unavailable",
        "invalid_arguments",
        "connection_lost",
        "reconnect_failed",
        "command_failed",
    ]
    message: str
