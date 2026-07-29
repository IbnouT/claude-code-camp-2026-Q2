"""Readable views over typed MCP tool-result envelopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping


EnvelopeKind = Literal["observation", "error"]


@dataclass(frozen=True)
class ToolResultView:
    """Human text plus the recognized envelope kind, when present."""

    text: str
    kind: EnvelopeKind | None = None
    complete: bool | None = None
    code: str | None = None

    @property
    def is_error(self) -> bool:
        return self.kind == "error"


def view_tool_result(result: Any) -> ToolResultView:
    """Decode gateway envelopes without consuming arbitrary JSON tool output."""
    original = str(result or "")
    candidate = original
    error_prefix = candidate.startswith("error: ")
    if error_prefix:
        candidate = candidate.removeprefix("error: ").lstrip()

    value: Any = result
    if isinstance(result, str):
        if not candidate.startswith("{"):
            return ToolResultView(original)
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            return ToolResultView(original)

    if not isinstance(value, Mapping):
        return ToolResultView(original)

    kind = value.get("type")
    if kind == "observation" and isinstance(value.get("text"), str):
        complete = value.get("complete")
        return ToolResultView(
            text=value["text"],
            kind="observation",
            complete=complete if isinstance(complete, bool) else None,
        )
    if kind == "error" and isinstance(value.get("message"), str):
        raw_code = value.get("code")
        code = str(raw_code) if raw_code else None
        label = code.replace("_", " ") if code else "error"
        return ToolResultView(
            text=f"{label}: {value['message']}",
            kind="error",
            code=code,
        )
    return ToolResultView(original)
