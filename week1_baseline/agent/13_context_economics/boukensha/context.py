"""Context: the live conversation state, with context-window management.

The one mutable holder in the data model. It carries the system prompt and the
ordered message history (all mutation goes through its methods), plus the token
accounting and compaction this step adds so a long session stays inside the
model's context window.
"""

from __future__ import annotations

from typing import Any

from .compaction import CompactionResult, _est_tokens, compact
from .journey import JourneyParser
from .message import Message, Role
from .usage import Usage, amplification


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
        #: Volume processed this turn: every input class plus output, summed
        #: across the turn's calls. Unchanged by caching.
        self.turn_tokens = 0
        #: The turn's four-class usage, so each metric reads from the classes.
        self.turn_usage = Usage()
        #: Billed cost for the turn, what a money ceiling measures.
        self.turn_cost = 0.0
        #: Session totals behind the amplification metric. ``unique_tokens`` counts
        #: each distinct thing sent ONCE (the un-shrinkable prefix, then every new
        #: message), while ``session_volume`` counts everything processed. Their
        #: ratio says how much of the bill is repetition rather than new work.
        self.unique_tokens = 0
        self.session_volume = 0
        self._prefix_counted = False
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
        # A message is new information exactly once, however many calls re-send it.
        self.unique_tokens += _est_tokens(message)

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
        """Zero every per-turn quantity at the top of a turn."""
        self.turn_tokens = 0
        self.turn_usage = Usage()
        self.turn_cost = 0.0

    def add_turn_tokens(self, input_tokens: int | None,
                        output_tokens: int | None) -> None:
        """Add a call's fresh input and output. Kept for callers holding only two
        counts; :meth:`add_turn_usage` is the four-class path."""
        self.turn_tokens += int(input_tokens or 0) + int(output_tokens or 0)

    def add_turn_usage(self, usage) -> None:
        """Accumulate one call's four-class usage into the turn.

        ``turn_tokens`` counts VOLUME PROCESSED, every input class plus output,
        so turning caching on does not move it. Counting only fresh input would
        make the same work look smaller once cached, which silently changes what
        a token ceiling means.
        """
        self.turn_usage = self.turn_usage + usage
        self.turn_tokens += usage.volume
        self.session_volume += usage.volume

    def count_prefix_once(self, prefix_tokens: int) -> None:
        """Count the un-shrinkable prefix as unique information, one time.

        The system prompt and the tool schemas are sent on every call but are new
        exactly once, which is the whole point of the amplification metric.
        """
        if prefix_tokens and not self._prefix_counted:
            self.unique_tokens += int(prefix_tokens)
            self._prefix_counted = True

    def amplification(self) -> float | None:
        """Volume processed per unique token, or None before anything is sent."""
        return amplification(self.session_volume, self.unique_tokens)

    def add_turn_cost(self, amount: float) -> None:
        """Accumulate billed cost for the turn, the quantity a money ceiling
        measures. Unpriced calls add nothing rather than a false zero."""
        self.turn_cost += float(amount or 0.0)

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
