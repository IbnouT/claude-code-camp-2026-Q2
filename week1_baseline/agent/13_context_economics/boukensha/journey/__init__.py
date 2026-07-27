"""The journey layer: parse MUD output into state, present it as readable cards.

Two framework-free modules behind one namespace. :mod:`parser` accumulates the
journey state (vitals, character, status) that feeds the header, and
:mod:`present` turns logger events into the readable cards the TUI draws. They
live together because they are the MUD-aware layer a front-end builds on, kept
apart from the generic Textual rendering in :mod:`boukensha.tui`.
"""

from .parser import JourneyParser, JourneyState
from .present import (
    ActionCard,
    Card,
    DIRECTIONS,
    Presenter,
    RoomCard,
    ThinkingCard,
    bare_tool_name,
    humanize_action,
    strip_ansi,
)

__all__ = [
    "JourneyParser",
    "JourneyState",
    "Presenter",
    "Card",
    "RoomCard",
    "ActionCard",
    "ThinkingCard",
    "humanize_action",
    "strip_ansi",
    "bare_tool_name",
    "DIRECTIONS",
]
