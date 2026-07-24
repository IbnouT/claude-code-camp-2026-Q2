"""Context: the live conversation state.

The one mutable holder in the data model. It carries the system prompt and the
ordered message history; all mutation goes through its methods.
"""

from __future__ import annotations

from .message import Message


class Context:
    """System prompt plus an ordered history of messages."""

    def __init__(self, system: str | None = None) -> None:
        self.system = system
        self.messages: list[Message] = []

    def add(self, message: Message) -> None:
        """Append a validated message to the history."""
        if not isinstance(message, Message):
            raise TypeError(
                f"Context.add expects a Message, got {type(message).__name__}"
            )
        self.messages.append(message)

    def __str__(self) -> str:
        return f"<Context turns={len(self.messages)}>"

    __repr__ = __str__
