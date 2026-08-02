"""Typed MCP result decoding and model-facing rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping, cast


EnvelopeKind = Literal["observation", "error"]
ResultMode = Literal["raw", "minimal", "full"]
RESULT_MODES: tuple[ResultMode, ...] = ("raw", "minimal", "full")


class TransformedToolResult(str):
    """Model-facing text carrying the complete transformation evidence."""

    evidence_stages: dict[str, Any]

    def __new__(
        cls,
        value: str,
        *,
        source: str,
        rendered: str,
        mode: ResultMode,
        error: bool,
        truncated_chars: int,
    ) -> "TransformedToolResult":
        instance = super().__new__(cls, value)
        instance.evidence_stages = {
            "mcp_result": source,
            "result_mode": mode,
            "rendered_result": rendered,
            "truncated_chars": truncated_chars,
            "model_input": value,
            "error": error,
        }
        return instance


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


def render_tool_result(result: Any, mode: ResultMode | str) -> str:
    """Shape one recognized envelope for the model, leaving evidence untouched."""
    if mode not in RESULT_MODES:
        raise ValueError(
            f"result mode must be one of {', '.join(RESULT_MODES)}, got {mode!r}"
        )
    original = str(result or "")
    if mode == "full":
        return original

    view = view_tool_result(result)
    if view.kind is None:
        return original
    if mode == "raw":
        return view.text

    payload: dict[str, Any] = {"text": view.text}
    if view.kind == "observation" and view.complete is not None:
        payload["complete"] = view.complete
    elif view.kind == "error":
        payload["complete"] = False
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def result_mode(value: str) -> ResultMode:
    """Validate a configuration value and return its narrowed type."""
    if value not in RESULT_MODES:
        raise ValueError(
            f"result mode must be one of {', '.join(RESULT_MODES)}, got {value!r}"
        )
    return cast(ResultMode, value)
