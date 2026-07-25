"""Google Gemini generateContent backend."""

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

class Gemini(Backend):
    provider_name = "gemini"
    api_key_env = "GEMINI_API_KEY"

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def build_request(self, context: Context, tools: Sequence[Tool] = (),
                      max_output_tokens: int = 1024,
                      thinking: str | None = None) -> dict[str, Any]:
        generation_config: dict[str, Any] = {"maxOutputTokens": max_output_tokens}
        if thinking is not None and self.thinking_mode == "level":
            level = self._resolve_thinking_level(thinking)
            if level is not None:
                generation_config["thinkingConfig"] = {"thinkingLevel": level}

        body: dict[str, Any] = {
            "contents": self._contents(context),
            "generationConfig": generation_config,
        }
        if context.system:
            body["systemInstruction"] = {"parts": [{"text": context.system}]}
        if tools:
            body["tools"] = [{
                "functionDeclarations": [self._declaration(t) for t in tools],
            }]
        return body

    def headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "x-goog-api-key": self.api_key or "",
        }

    def url(self) -> str:
        return f"{self.BASE_URL}/{self.model}:generateContent"

    # -- response normalization --------------------------------------------

    def parse_response(self, response: dict[str, Any]) -> ParsedResponse:
        """Read a generateContent reply.

        The first candidate's ``content.parts`` are each a ``text`` part or a
        ``functionCall`` part (``name``, ``args``). Gemini assigns no call id,
        so the function name doubles as ``ToolUseBlock.id`` (Gemini also keys a
        functionResponse back to its call by name). Any functionCall present
        means the stop reason is ``"tool_use"``.
        Source: https://ai.google.dev/api/generate-content
        """
        candidates = response.get("candidates") or []
        parts = []
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
        content: list[Any] = []
        tool_used = False
        for part in parts:
            call = part.get("functionCall")
            if call:
                name = call["name"]
                content.append(ToolUseBlock(name, name, call.get("args") or {}))
                tool_used = True
            elif part.get("text"):
                content.append(TextBlock(part["text"]))
        return ParsedResponse("tool_use" if tool_used else "end_turn", tuple(content))

    # -- translation -------------------------------------------------------

    def _contents(self, context: Context) -> list[dict[str, Any]]:
        wire = []
        for message in context.messages:
            if message.role is Role.TOOL_RESULT:
                wire.append({
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": block.tool_name,
                                "id": block.tool_use_id,
                                "response": {"result": block.content},
                            }
                        }
                        for block in message.content
                        if isinstance(block, ToolResultBlock)
                    ],
                })
            else:
                role = "model" if message.role is Role.ASSISTANT else "user"
                wire.append({
                    "role": role,
                    "parts": [self._part(b) for b in message.content],
                })
        return wire

    @staticmethod
    def _part(block: Any) -> dict[str, Any]:
        if isinstance(block, TextBlock):
            return {"text": block.text}
        if isinstance(block, ToolUseBlock):
            return {
                "functionCall": {
                    "name": block.name,
                    "id": block.id,
                    "args": block.input,
                }
            }
        raise ValueError(f"unsupported block for Gemini: {type(block).__name__}")

    def _declaration(self, tool: Tool) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": self._json_schema(tool),
        }
