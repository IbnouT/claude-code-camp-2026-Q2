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
class ToolUseBlock:
    """The model requesting a tool call."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResultBlock:
    """A tool's output, linked to the call that produced it."""

    tool_use_id: str
    content: str


Block = Union[TextBlock, ToolUseBlock, ToolResultBlock]


@dataclass(frozen=True)
class Message:
    """One conversation entry: a role and a tuple of content blocks.

    Content passed as a string, a single block, or a sequence of blocks is
    normalized to a tuple. Three invariants are enforced at construction; each
    rejects data that could never form a valid request:

    * a ``tool_result`` message carries only ``ToolResultBlock``s, each with a
      non-empty ``tool_use_id``;
    * no other role carries a ``ToolResultBlock``;
    * a ``ToolUseBlock`` appears only in an ``assistant`` message.
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
        if isinstance(content, (TextBlock, ToolUseBlock, ToolResultBlock)):
            return (content,)
        return tuple(content)

    def _validate(self) -> None:
        if not isinstance(self.role, Role):
            raise ValueError(f"role must be a Role, got {self.role!r}")

        for block in self.content:
            if not isinstance(block, (TextBlock, ToolUseBlock, ToolResultBlock)):
                raise ValueError(
                    f"content elements must be typed blocks, got {type(block).__name__}"
                )

        has_tool_result = any(isinstance(b, ToolResultBlock) for b in self.content)
        has_tool_use = any(isinstance(b, ToolUseBlock) for b in self.content)

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

    # -- convenience constructors -----------------------------------------

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(Role.USER, text)

    @classmethod
    def assistant(cls, content: Any) -> Message:
        return cls(Role.ASSISTANT, content)

    @classmethod
    def tool_result(cls, tool_use_id: str, content: str) -> Message:
        return cls(Role.TOOL_RESULT, ToolResultBlock(tool_use_id, content))

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
            if isinstance(block, ToolUseBlock):
                return f"ToolUseBlock({block.name})"
            return f"ToolResultBlock({block.tool_use_id})"

        parts = ", ".join(preview(b) for b in self.content)
        return f"<Message role={self.role.value} content=[{parts}]>"

    __repr__ = __str__
