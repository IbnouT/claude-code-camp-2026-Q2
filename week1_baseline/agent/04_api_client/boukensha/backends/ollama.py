"""Ollama local chat backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from ..message import Role, TextBlock, ToolResultBlock, ToolUseBlock
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
