"""Ollama local chat backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from ..message import (
    ParsedResponse,
    Role,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from .base import Backend

if TYPE_CHECKING:
    from ..context import Context
    from ..tool import Tool

class Ollama(Backend):
    provider_name = "ollama"
    api_key_env = None

    BASE_URL = "http://localhost:11434"

    def build_request(self, context: Context, tools: Sequence[Tool] = (),
                      max_output_tokens: int = 1024,
                      thinking: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": self._messages(context),
            "options": {"num_predict": max_output_tokens},
        }
        if tools:
            body["tools"] = [self._tool(t) for t in tools]
        if thinking is not None and self.thinking_mode:
            level = self._resolve_thinking_level(thinking)
            if level is not None and self.thinking_mode == "level_string":
                body["think"] = level
            elif level is not None and self.thinking_mode == "flag":
                # A boolean toggle: "none" turns thinking off, any level on.
                body["think"] = level != "none"
        return body

    def headers(self) -> dict[str, str]:
        return {"content-type": "application/json"}

    def url(self) -> str:
        return f"{self.BASE_URL}/api/chat"

    # -- response normalization --------------------------------------------

    def parse_response(self, response: dict[str, Any]) -> ParsedResponse:
        """Read an ``/api/chat`` reply.

        The ``message`` object holds ``content`` (text, empty when a call is
        present) and ``tool_calls[].function`` (``name``, ``arguments`` object).
        Ollama assigns no call id, so the function name doubles as
        ``ToolUseBlock.id`` (Ollama also matches a tool result back to its call
        by name). Any tool_call present means the stop reason is ``"tool_use"``.
        OllamaCloud shares this wire format and inherits this method.
        Source: https://github.com/ollama/ollama/blob/main/docs/api.md
        """
        message = response.get("message") or {}
        content: list[Any] = []
        text = message.get("content")
        if text:
            content.append(TextBlock(text))
        tool_calls = message.get("tool_calls") or []
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn["name"]
            content.append(ToolUseBlock(name, name, fn.get("arguments") or {}))
        return ParsedResponse(
            "tool_use" if tool_calls else "end_turn", tuple(content)
        )

    # -- translation -------------------------------------------------------

    def _messages(self, context: Context) -> list[dict[str, Any]]:
        wire: list[dict[str, Any]] = []
        if context.system:
            wire.append({"role": "system", "content": context.system})
        for message in context.messages:
            if message.role is Role.TOOL_RESULT:
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        wire.append({
                            "role": "tool",
                            "content": block.content,
                            "tool_name": block.tool_name,
                        })
                continue

            entry: dict[str, Any] = {
                "role": message.role.value,
                "content": "\n".join(
                    b.text for b in message.content if isinstance(b, TextBlock)
                ),
            }
            calls = [
                {"function": {"name": b.name, "arguments": b.input}}
                for b in message.content
                if isinstance(b, ToolUseBlock)
            ]
            if calls:
                entry["tool_calls"] = calls
            wire.append(entry)
        return wire

    def _tool(self, tool: Tool) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": self._json_schema(tool),
            },
        }
