"""Anthropic Messages API backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from ..message import Role, TextBlock, ToolResultBlock, ToolUseBlock
from .base import Backend

if TYPE_CHECKING:
    from ..context import Context
    from ..tool import Tool

#: budget_tokens for models whose catalog thinking mode is "budget".
THINKING_BUDGETS = {"low": 1024, "medium": 4096, "high": 16384}


class Anthropic(Backend):
    provider_name = "anthropic"
    api_key_env = "ANTHROPIC_API_KEY"

    BASE_URL = "https://api.anthropic.com/v1/messages"

    def build_request(self, context: Context, tools: Sequence[Tool] = (),
                      max_output_tokens: int = 1024,
                      thinking: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_output_tokens,
            "messages": self._messages(context),
        }
        if context.system:
            body["system"] = context.system
        if tools:
            body["tools"] = [self._tool(t) for t in tools]
        if thinking is not None and self.thinking_mode:
            if self.thinking_mode == "adaptive":
                if thinking == "none" and self.thinking_default != "always_on":
                    # Models that default off or on both accept an explicit
                    # disable. Explicit is required for the on-by-default case
                    # and safe for the off case.
                    body["thinking"] = {"type": "disabled"}
                else:
                    # Always-on models cannot be disabled, so "none" lands at
                    # the lowest effort rather than off.
                    level = self._resolve_thinking_level(thinking)
                    if level is not None:
                        body["thinking"] = {"type": "adaptive"}
                        body["output_config"] = {"effort": level}
            elif self.thinking_mode == "budget" and thinking != "none":
                # Extended thinking is opt-in, so "none" means omit the field.
                level = self._resolve_thinking_level(thinking)
                if level is not None:
                    body["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": THINKING_BUDGETS[level],
                    }
        return body

    def headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }

    def url(self) -> str:
        return self.BASE_URL

    # -- translation -------------------------------------------------------

    def _messages(self, context: Context) -> list[dict[str, Any]]:
        wire = []
        for message in context.messages:
            if message.role is Role.TOOL_RESULT:
                wire.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.tool_use_id,
                            "content": block.content,
                        }
                        for block in message.content
                        if isinstance(block, ToolResultBlock)
                    ],
                })
            else:
                wire.append({
                    "role": message.role.value,
                    "content": [self._block(b) for b in message.content],
                })
        return wire

    @staticmethod
    def _block(block: Any) -> dict[str, Any]:
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ToolUseBlock):
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }
        raise ValueError(f"unsupported block for Anthropic: {type(block).__name__}")

    def _tool(self, tool: Tool) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": self._json_schema(tool),
        }

