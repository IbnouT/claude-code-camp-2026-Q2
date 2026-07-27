"""Conversation data: roles, typed content blocks, and messages.

Message content is always a tuple of typed blocks. Plain text is normalized to
a single ``TextBlock`` at construction, so every downstream component reads one
provider-neutral shape and each backend translates at its own edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union


class Role(str, Enum):
    """The allowed conversation roles."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"


@dataclass(frozen=True)
class TextBlock:
    """Plain text."""

    text: str


@dataclass(frozen=True)
class ReasoningBlock:
    """A model's thinking output, normalized across providers.

    ``text`` is the human-readable reasoning and may be empty (redacted or
    omitted reasoning). ``signature`` is an opaque provider token carried only
    so the block can be echoed back unchanged on providers that require it
    (Anthropic thinking signatures, Gemini ``thoughtSignature``); it is never
    interpreted. ``redacted`` marks Anthropic ``redacted_thinking``, whose
    payload rides in ``signature``.
    """

    text: str
    signature: str | None = None
    redacted: bool = False


@dataclass(frozen=True)
class ToolUseBlock:
    """The model requesting a tool call.

    ``signature`` is an opaque provider token carried only for round-trip on
    providers that attach one to the call (Gemini pins a ``thoughtSignature``
    to the ``functionCall`` part and requires it echoed back); it is never
    interpreted and stays ``None`` on providers that assign none.
    """

    id: str
    name: str
    input: dict[str, Any]
    signature: str | None = None


@dataclass(frozen=True)
class ToolResultBlock:
    """A tool's output, linked to the call that produced it.

    Carries both halves of the link: the call id and the tool's name, set when
    the result is created. Backends that key results by name read it directly.
    """

    tool_use_id: str
    tool_name: str
    content: str


Block = Union[TextBlock, ReasoningBlock, ToolUseBlock, ToolResultBlock]


@dataclass(frozen=True)
class ParsedResponse:
    """A provider reply normalized to the common shape the loop reads.

    Every backend's ``parse_response`` returns this: a stop reason and a tuple
    of the same typed content blocks the rest of the data model uses, so the
    loop builds an assistant ``Message`` from ``content`` with no dict step.
    ``stop_reason`` is ``"tool_use"`` when the model asked for a tool and
    ``"end_turn"`` otherwise. ``content`` holds ``ReasoningBlock``,
    ``TextBlock``, and ``ToolUseBlock`` in the order the provider emitted them,
    so a thinking block that leads an assistant turn stays first and can be
    echoed back in position; ``ToolResultBlock`` never appears here.
    """

    stop_reason: str
    content: tuple[Block, ...] = ()

    def __post_init__(self) -> None:
        if self.stop_reason not in ("tool_use", "end_turn"):
            raise ValueError(
                f"stop_reason must be 'tool_use' or 'end_turn', "
                f"got {self.stop_reason!r}"
            )
        for block in self.content:
            if not isinstance(block, (TextBlock, ReasoningBlock, ToolUseBlock)):
                raise ValueError(
                    f"a parsed response holds ReasoningBlock, TextBlock, and "
                    f"ToolUseBlock, got {type(block).__name__}"
                )

    def __str__(self) -> str:
        kinds = ", ".join(type(b).__name__ for b in self.content)
        return f"<ParsedResponse stop_reason={self.stop_reason} content=[{kinds}]>"

    __repr__ = __str__


@dataclass(frozen=True)
class Message:
    """One conversation entry: a role and a tuple of content blocks.

    Content passed as a string, a single block, or a sequence of blocks is
    normalized to a tuple. Four invariants are enforced at construction; each
    rejects data that could never form a valid request:

    * a ``tool_result`` message carries only ``ToolResultBlock``s, each with a
      non-empty ``tool_use_id``;
    * no other role carries a ``ToolResultBlock``;
    * a ``ToolUseBlock`` appears only in an ``assistant`` message;
    * a ``ReasoningBlock`` appears only in an ``assistant`` message.
    """

    role: Role
    content: tuple[Block, ...] = field(default=())

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", self._normalize(self.content))
        self._validate()

    @staticmethod
    def _normalize(content: Any) -> tuple[Block, ...]:
        if isinstance(content, str):
            return (TextBlock(content),)
        if isinstance(content, (TextBlock, ReasoningBlock, ToolUseBlock,
                                ToolResultBlock)):
            return (content,)
        return tuple(content)

    def _validate(self) -> None:
        if not isinstance(self.role, Role):
            raise ValueError(f"role must be a Role, got {self.role!r}")

        for block in self.content:
            if not isinstance(block, (TextBlock, ReasoningBlock, ToolUseBlock,
                                      ToolResultBlock)):
                raise ValueError(
                    f"content elements must be typed blocks, got {type(block).__name__}"
                )

        has_tool_result = any(isinstance(b, ToolResultBlock) for b in self.content)
        has_tool_use = any(isinstance(b, ToolUseBlock) for b in self.content)
        has_reasoning = any(isinstance(b, ReasoningBlock) for b in self.content)

        if self.role is Role.TOOL_RESULT:
            results = [b for b in self.content if isinstance(b, ToolResultBlock)]
            if not results:
                raise ValueError(
                    "a tool_result message must carry at least one ToolResultBlock"
                )
            if any(not b.tool_use_id for b in results):
                raise ValueError(
                    "a tool_result message requires a non-empty tool_use_id"
                )
            if any(not b.tool_name for b in results):
                raise ValueError(
                    "a tool_result message requires a non-empty tool_name"
                )
            if any(not isinstance(b, ToolResultBlock) for b in self.content):
                raise ValueError(
                    "a tool_result message carries only ToolResultBlocks"
                )
        elif has_tool_result:
            raise ValueError(
                f"only a tool_result message may carry a ToolResultBlock, "
                f"not role {self.role.value}"
            )

        if has_tool_use and self.role is not Role.ASSISTANT:
            raise ValueError(
                f"a ToolUseBlock may only appear in an assistant message, "
                f"not role {self.role.value}"
            )

        if has_reasoning and self.role is not Role.ASSISTANT:
            raise ValueError(
                f"a ReasoningBlock may only appear in an assistant message, "
                f"not role {self.role.value}"
            )

    # -- convenience constructors -----------------------------------------

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(Role.USER, text)

    @classmethod
    def assistant(cls, content: Any) -> Message:
        return cls(Role.ASSISTANT, content)

    @classmethod
    def tool_result(cls, tool_use_id: str, tool_name: str,
                    content: str) -> Message:
        return cls(Role.TOOL_RESULT, ToolResultBlock(tool_use_id, tool_name, content))

    # -- accessors ---------------------------------------------------------

    @property
    def tool_use_ids(self) -> tuple[str, ...]:
        """The tool-call ids this message answers (plural for parallel calls)."""
        return tuple(
            b.tool_use_id for b in self.content if isinstance(b, ToolResultBlock)
        )

    def __str__(self) -> str:
        def preview(block: Block) -> str:
            if isinstance(block, TextBlock):
                text = block.text if len(block.text) <= 40 else block.text[:37] + "..."
                return f"TextBlock({text!r})"
            if isinstance(block, ReasoningBlock):
                tag = "redacted" if block.redacted else "signed" if block.signature else "plain"
                return f"ReasoningBlock({tag})"
            if isinstance(block, ToolUseBlock):
                return f"ToolUseBlock({block.name})"
            return f"ToolResultBlock({block.tool_use_id})"

        parts = ", ".join(preview(b) for b in self.content)
        return f"<Message role={self.role.value} content=[{parts}]>"

    __repr__ = __str__
