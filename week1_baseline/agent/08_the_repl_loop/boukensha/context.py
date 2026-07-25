"""Context: the live conversation state.

The one mutable holder in the data model. It carries the system prompt and the
ordered message history; all mutation goes through its methods.
"""

from __future__ import annotations

from .message import Message, Role


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

    def clear_messages(self) -> None:
        """Drop all conversation history, keeping the system prompt.

        The REPL's ``/clear`` command uses this to start a fresh conversation
        without rebuilding the session: tools stay registered in the registry
        (a separate owner) and the system prompt is untouched.
        """
        self.messages = []

    def drop_last_turn(self) -> str | None:
        """Remove the most recent user message and everything after it.

        Returns the removed user text, or ``None`` when there is no user
        message to drop. The REPL's ``/undo`` and ``/retry`` use this to walk a
        turn back without wiping the whole history the way ``/clear`` does. The
        mutation lives here because ``Context`` owns the history.
        """
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role is Role.USER:
                removed = self.messages[i]
                text = "".join(getattr(b, "text", "") for b in removed.content)
                self.messages = self.messages[:i]
                return text
        return None

    def __str__(self) -> str:
        return f"<Context turns={len(self.messages)}>"

    __repr__ = __str__
