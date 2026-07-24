"""OpenAI Responses API backend."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Sequence

from ..message import Role, TextBlock, ToolResultBlock, ToolUseBlock
from .base import Backend

if TYPE_CHECKING:
    from ..context import Context
    from ..tool import Tool


class OpenAI(Backend):
    provider_name = "openai"
    api_key_env = "OPENAI_API_KEY"

    BASE_URL = "https://api.openai.com/v1/responses"

    def build_request(self, context: Context, tools: Sequence[Tool] = (),
                      max_output_tokens: int = 1024,
                      thinking: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "input": self._input_items(context),
            "max_output_tokens": max_output_tokens,
        }
        if context.system:
            body["instructions"] = context.system
        if tools:
            body["tools"] = [self._tool(t) for t in tools]
        if thinking is not None and self.thinking_mode == "effort":
            level = self._resolve_thinking_level(thinking)
            if level is not None:
                body["reasoning"] = {"effort": level}
        return body

    def headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}",
        }

    def url(self) -> str:
        return self.BASE_URL

    # -- translation -------------------------------------------------------

    def _input_items(self, context: Context) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in context.messages:
            if message.role is Role.TOOL_RESULT:
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        items.append({
                            "type": "function_call_output",
                            "call_id": block.tool_use_id,
                            "output": block.content,
                        })
                continue

            texts = [b.text for b in message.content if isinstance(b, TextBlock)]
            if texts:
                items.append({
                    "role": message.role.value,
                    "content": "\n".join(texts),
                })
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    items.append({
                        "type": "function_call",
                        "call_id": block.id,
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    })
        return items

    def _tool(self, tool: Tool) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": self._json_schema(tool),
        }
