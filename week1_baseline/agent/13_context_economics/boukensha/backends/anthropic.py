"""Anthropic Messages API backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from ..message import (
    ParsedResponse,
    ReasoningBlock,
    Role,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from .base import Backend

if TYPE_CHECKING:
    from ..context import Context
    from ..tool import Tool

#: budget_tokens for models whose catalog thinking mode is "budget".
THINKING_BUDGETS = {"low": 1024, "medium": 4096, "high": 16384}


class Anthropic(Backend):

    #: Anthropic caches an explicit prefix, billed per the catalog's cache classes.
    caches: ClassVar[bool] = True
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
        # Automatic prompt caching: one top-level field, and the provider places
        # the breakpoint at the last cacheable block and moves it forward as the
        # conversation grows. Preferred over hand-placed breakpoints because the
        # stable prefix here (system prompt plus tool schemas) is followed by a
        # history that grows every turn, which is exactly what it manages.
        # https://platform.claude.com/docs/en/build-with-claude/prompt-caching
        body["cache_control"] = {"type": "ephemeral"}
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
                    budget = THINKING_BUDGETS[level]
                    body["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget,
                    }
                    # Anthropic counts thinking tokens toward max_tokens and
                    # rejects a request unless budget_tokens < max_tokens
                    # (platform.claude.com/docs/en/build-with-claude/
                    # extended-thinking). The default cap (1024) sits at or
                    # below every budget, so honoring the dial means lifting
                    # the wire cap: max_output_tokens is the response
                    # allowance and max_tokens is budget + that allowance, so
                    # the budget always fits and the response room is kept.
                    body["max_tokens"] = budget + max_output_tokens
        return body

    def headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }

    def url(self) -> str:
        return self.BASE_URL

    # -- response normalization --------------------------------------------

    def parse_response(self, response: dict[str, Any]) -> ParsedResponse:
        """Read a Messages API reply.

        Top-level ``stop_reason`` is ``"tool_use"`` only when the model asked
        for a tool, everything else maps to ``"end_turn"``. Each ``content``
        block is a ``text`` block (a ``text`` field), a ``tool_use`` block
        (``id``, ``name``, ``input``), or a thinking block. ``thinking`` blocks
        become ``ReasoningBlock``s carrying the ``signature``, and
        ``redacted_thinking`` blocks a redacted ``ReasoningBlock`` whose opaque
        ``data`` rides in ``signature``. Block order is preserved, so a leading
        thinking block stays first for the round trip below.
        Source: https://platform.claude.com/docs/en/api/messages ,
        https://platform.claude.com/docs/en/build-with-claude/thinking
        """
        stop_reason = "tool_use" if response.get("stop_reason") == "tool_use" else "end_turn"
        content: list[Any] = []
        for block in response.get("content") or []:
            kind = block.get("type")
            if kind == "text":
                text = block.get("text") or ""
                if text:
                    content.append(TextBlock(text))
            elif kind == "thinking":
                content.append(ReasoningBlock(
                    block.get("thinking") or "", block.get("signature")
                ))
            elif kind == "redacted_thinking":
                content.append(ReasoningBlock(
                    "", block.get("data"), redacted=True
                ))
            elif kind == "tool_use":
                content.append(ToolUseBlock(
                    block["id"], block["name"], block.get("input") or {}
                ))
        return ParsedResponse(stop_reason, tuple(content))

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
        if isinstance(block, ReasoningBlock):
            # Re-emit the native thinking block unchanged. The API verifies the
            # signature and rejects any request whose latest assistant turn has
            # a modified or dropped thinking block (400 invalid_request_error,
            # "thinking or redacted_thinking blocks in the latest assistant
            # message cannot be modified"), so the block must round-trip
            # verbatim when tool results are returned on the same model.
            # Source: platform.claude.com/docs/en/build-with-claude/
            # thinking-troubleshooting
            if block.redacted:
                return {"type": "redacted_thinking", "data": block.signature}
            return {
                "type": "thinking",
                "thinking": block.text,
                "signature": block.signature,
            }
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

