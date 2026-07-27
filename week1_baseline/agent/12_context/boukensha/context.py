"""Context: the live conversation state, with context-window management.

The one mutable holder in the data model. It carries the system prompt and the
ordered message history (all mutation goes through its methods), plus the token
accounting and compaction this step adds so a long session stays inside the
model's context window.
"""

from __future__ import annotations

from typing import Any

from .compaction import CompactionResult, compact
from .journey import JourneyParser
from .message import Message, Role


class Context:
    """System prompt, an ordered history, and its context-window accounting."""

    def __init__(self, system: str | None = None,
                 context_window: int = 200_000,
                 compaction_threshold: float = 0.85) -> None:
        self.system = system
        self.messages: list[Message] = []
        #: The model's input capacity, so usage can be measured as a fraction.
        self.context_window = context_window
        #: Fraction of the window at which the loop compacts before the next call.
        self.compaction_threshold = compaction_threshold
        #: Estimated tokens currently in the window (set from the last usage).
        self.current_tokens = 0
        #: Tokens spent this turn, summed across the turn's model calls.
        self.turn_tokens = 0
        #: The session's parsed structure, fed the agent's tool activity. It
        #: persists across turns beside the history it summarizes, so both
        #: auto-compaction and /compact read it. This is the parser graduating
        #: from a TUI helper to the agent's memory (see boukensha.compaction).
        self.journey = JourneyParser()
        #: The most recent compaction's detail, for logging and the TUI card.
        self.last_compaction: CompactionResult | None = None

    # -- history -----------------------------------------------------------

    def add(self, message: Message) -> None:
        """Append a validated message to the history."""
        if not isinstance(message, Message):
            raise TypeError(
                f"Context.add expects a Message, got {type(message).__name__}"
            )
        self.messages.append(message)

    def clear_messages(self) -> None:
        """Drop all history, keeping the system prompt, and reset the window."""
        self.messages = []
        self.current_tokens = 0

    def drop_last_turn(self) -> str | None:
        """Remove the most recent user message and everything after it.

        Returns the removed user text, or ``None`` when there is no user
        message to drop. The REPL's ``/undo`` and ``/retry`` use it.
        """
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role is Role.USER:
                removed = self.messages[i]
                text = "".join(getattr(b, "text", "") for b in removed.content)
                self.messages = self.messages[:i]
                return text
        return None

    # -- token accounting --------------------------------------------------

    def update_tokens(self, n: int | None) -> None:
        """Set the current window occupancy from the latest reported usage."""
        self.current_tokens = int(n or 0)

    def reset_turn_tokens(self) -> None:
        self.turn_tokens = 0

    def add_turn_tokens(self, input_tokens: int | None,
                        output_tokens: int | None) -> None:
        self.turn_tokens += int(input_tokens or 0) + int(output_tokens or 0)

    def usage_fraction(self) -> float:
        if self.context_window <= 0:
            return 0.0
        return self.current_tokens / self.context_window

    def usage_pct(self) -> int:
        return round(self.usage_fraction() * 100)

    # -- compaction --------------------------------------------------------

    def needs_compaction(self, threshold: float | None = None) -> bool:
        """Whether window pressure has reached the compaction threshold."""
        limit = self.compaction_threshold if threshold is None else threshold
        return self.usage_fraction() >= limit

    def compact_messages(self, keep_recent: int = 2,
                         overhead: int = 0) -> int:
        """Compact the history structure-aware and reset occupancy. Returns how
        many messages were dropped (compression and summary are additional, see
        :attr:`last_compaction`).

        Delegates to the :mod:`boukensha.compaction` pipeline: compress old
        tool-result bodies to stubs, drop the oldest whole turns if still over
        the token target, then distil what was shed into one memory note from
        the journey state. The survivor prefix always starts on a user turn, so
        a tool_result is never orphaned from its tool_use and no request begins
        on a non-user role. The system prompt lives outside ``messages`` and is
        never dropped.
        """
        result = compact(self.messages, self.journey.state,
                         window=self.context_window, overhead=overhead,
                         keep_recent=keep_recent)
        self.messages = result.messages
        self.last_compaction = result
        self.current_tokens = 0
        return result.dropped

    def feed_tool_call(self, name: Any, args: Any, call_id: Any) -> None:
        """Feed the journey memory a dispatched tool call (agent thread only)."""
        self.journey.on_tool_call(name, args, call_id)

    def feed_tool_result(self, name: Any, result: Any, call_id: Any) -> None:
        """Feed the journey memory a tool result (agent thread only)."""
        self.journey.on_tool_result(name, result, call_id)

    def __str__(self) -> str:
        return (
            f"<Context turns={len(self.messages)} window={self.context_window} "
            f"current={self.current_tokens}>"
        )

    __repr__ = __str__
