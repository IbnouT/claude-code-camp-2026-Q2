"""Present: turn raw logger events into readable journey beats.

The TUI shows a human journey, not a debug log, so the noisy end-to-end trace
(prompt sizes, iteration counters, token counts, raw tool names with JSON args)
must never reach it. That separation is enforced HERE, at one boundary: the
presenter consumes the same logger events the TUI subscribes to and emits only
three kinds of card, the beats a reader cares about.

- ``RoomCard``   the MUD's room narration: title, description, exits.
- ``ActionCard`` what the agent did, humanized: ``move west``, ``look``,
  ``attack the fido`` (the ``tbamud__`` prefix and JSON args are stripped).
- ``ThinkingCard`` the agent's reasoning or objective, kept apart from MUD prose.

Plumbing events (``prompt``, ``iteration``, ``response``, token usage) produce
NO card, so the raw trace cannot leak into the TUI by construction. The full
trace still lives in the JSONL log and the step-13 log viewer, which own the
technical flow.

Framework-free by design (no Textual import): the presenter is unit-tested with
plain event dicts, and the generic renderer in :mod:`boukensha.tui` consumes the
cards it returns without knowing anything about a MUD.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# The MUD wraps every line in terminal color escapes; they carry no meaning for
# a text card and render as garbage, so they are stripped before display.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b[()][0-9A-B]|\x1b[=>]")
EXITS_RE = re.compile(r"^\[ Exits: ([^\]]+)\]", re.MULTILINE)
# The tbaMUD game prompt line, e.g. ``24H 100M 85V (news) (motd) >``. It is
# telemetry, not narration, so it is dropped from a room's displayed body.
PROMPT_LINE_RE = re.compile(r"^\s*\d+H \d+M \d+V\b.*>\s*$")

#: Tools whose result is a room description (the presenter renders a RoomCard).
ROOM_TOOLS = frozenset({"look", "move"})
#: Lines that are unmistakably combat. Detection is windowed like the week0
#: visualizer: a fight is "on" only while such lines keep arriving, so it turns
#: itself off when they stop (a disconnect, a login menu, moving on) instead of
#: sticking until an explicit death. Only these lines enter the fight box, so a
#: reconnect menu or an error can never leak into it.
COMBAT_LINE_RE = re.compile(
    r"fighting YOU|You're fighting|you are dead|is dead!|R\.I\.P\.|"
    r"mortally wounded|death cry|tries to hit you|hits? you|misses? you|"
    r"but miss(es)?|snaps? .* at you|you flee|flees|"
    r"you (barely |lightly )?(hit|swing|slash|pierce|pound|crush|whack|smite|"
    r"maul|claw|bite|tickle|thrust|cleave)",
    re.I)
#: A monster's death line, capturing the victim's name.
COMBAT_KILL_RE = re.compile(r"(.+?) is dead!\s*R\.I\.P\.")
#: Compass letters spelled out for readable exits and actions.
DIRECTIONS = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "u": "up", "d": "down",
    "north": "north", "south": "south", "east": "east", "west": "west",
    "up": "up", "down": "down",
}


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", str(text or ""))


def bare_tool_name(name) -> str:
    """The tool's own name without any MCP host prefix (``tbamud__look`` -> ``look``)."""
    return str(name or "").split("__")[-1]


def humanize_action(name, args) -> str:
    """A tool call as a short English phrase, no prefix and no JSON.

    Generic presentation of the call, never game knowledge: the verb is the
    tool name, and the one key argument (a direction, a target, a keyword) is
    appended in readable form. Unknown tools still read cleanly.
    """
    verb = bare_tool_name(name).replace("_", " ")
    args = args if isinstance(args, dict) else {}
    if verb == "move":
        direction = str(args.get("direction") or "").lower()
        return f"move {DIRECTIONS.get(direction, direction)}".strip()
    if verb in ("attack", "kill", "hit") and args.get("target"):
        return f"{verb} the {args['target']}"
    if verb in ("examine", "look") and (args.get("target") or args.get("keyword")):
        return f"{verb} {args.get('target') or args.get('keyword')}"
    # Fallback: verb plus the first argument value, if any, never the JSON.
    for value in args.values():
        if value not in (None, "", [], {}):
            return f"{verb} {value}"
    return verb


@dataclass
class Card:
    """One readable beat in the journey. ``kind`` drives styling in the TUI."""

    kind: str                       # "room" | "action" | "thinking" | "you" | "error"
    title: str = ""
    body: str = ""
    exits: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        head = self.title or self.body[:40]
        return f"<Card {self.kind} {head!r}>"

    __repr__ = __str__


def RoomCard(title: str, body: str, exits: list[str]) -> Card:
    return Card(kind="room", title=title, body=body, exits=exits)


def ActionCard(text: str) -> Card:
    return Card(kind="action", body=text)


def ThinkingCard(text: str) -> Card:
    return Card(kind="thinking", body=text)


class Presenter:
    """Consume logger events, emit readable :class:`Card` beats.

    Wire :meth:`on_event` as a ``logger.subscribe`` callback (or call it in
    tests). It appends to :attr:`cards` (the Feed's full history) and tracks the
    Dashboard's live state: the current room card, the recent actions, and the
    current thinking. NOT thread-safe by itself: the TUI posts events to its app
    thread and calls this there, matching the parser's thread rule.
    """

    #: How many recent actions the Dashboard's compact panel keeps.
    RECENT_ACTIONS = 3

    def __init__(self) -> None:
        self.cards: list[Card] = []
        self.current_room: Card | None = None
        #: The most recent NON-room MUD reply (examine, track, a failed move),
        #: shown under the room on the dashboard as an "as it happened" line.
        self.latest_message: str = ""
        self.recent_actions: list[Card] = []
        self.current_thinking: Card | None = None
        #: The standing objective: the latest instruction the user gave, shown
        #: pinned at the top of the side column while thinking updates below it.
        self.current_goal: str | None = None
        #: Combat state, driving the dashboard's fight box and the red pulse.
        #: ``combat_active`` is true mid-fight, ``combat_result`` is the outcome
        #: once it ends, and ``combat_lines`` is the blow-by-blow stream.
        self.combat_active = False
        self.combat_lines: list[str] = []
        self.combat_result: str | None = None
        self._pending: dict[str, dict] = {}

    def on_event(self, event: dict) -> list[Card]:
        """Route one logger event, returning any cards it produced (possibly none)."""
        phase = event.get("phase")
        if phase == "tool_call":
            return self._on_tool_call(event)
        if phase == "tool_result":
            return self._on_tool_result(event)
        if phase in ("response", "reasoning", "plan"):
            # The agent's dynamic text: its per-iteration commentary and its
            # final summary both arrive as response text, so the thinking view
            # tracks the CURRENT view and never goes stale on an old summary.
            return self._set_thinking(event.get("text"))
        return []

    def add_user(self, text: str) -> Card:
        # The user's instruction is the agent's current goal until the next one.
        self.current_goal = str(text)
        card = Card(kind="you", body=str(text))
        self.cards.append(card)
        return card

    def add_reply(self, text: str) -> list[Card]:
        """The agent's routed reply text is its latest view, a thinking beat."""
        return self._set_thinking(text)

    def _set_thinking(self, text) -> list[Card]:
        """Update the current thinking from any agent text, deduped.

        Skips the ``(tool use: N)`` placeholder the agent logs for a tool-only
        turn, and skips text identical to the current thinking, because the
        final reply arrives twice (the response event and the routed reply)
        carrying the same words.
        """
        clean = self._clean(text)
        if not clean or clean.startswith("(tool use"):
            return []
        if self.current_thinking is not None and self.current_thinking.body == clean:
            return []
        card = ThinkingCard(clean)
        self.cards.append(card)
        self.current_thinking = card
        return [card]

    def add_error(self, text: str) -> Card:
        card = Card(kind="error", body=str(text))
        self.cards.append(card)
        return card

    # -- internals ---------------------------------------------------------

    def _on_tool_call(self, event: dict) -> list[Card]:
        call_id = str(event.get("id") or event.get("name"))
        self._pending[call_id] = {
            "name": event.get("name"), "args": event.get("args") or {}}
        card = ActionCard("-> " + humanize_action(event.get("name"),
                                                   event.get("args")))
        self.cards.append(card)
        self.recent_actions.append(card)
        del self.recent_actions[:-self.RECENT_ACTIONS]
        return [card]

    def _on_tool_result(self, event: dict) -> list[Card]:
        call = self._pending.pop(
            str(event.get("tool_use_id") or event.get("name")), None) or {}
        name = bare_tool_name(call.get("name") or event.get("name"))
        text = strip_ansi(event.get("result"))
        combat_card = self._absorb_combat(text)
        # A result that carried combat (mid-fight or just-ended) belongs to the
        # fight box, not the transient message line.
        is_combat_result = self.combat_active or combat_card is not None

        room = self._room_card(event.get("result")) if name in ROOM_TOOLS else None
        emitted: list[Card] = []
        if room is not None:
            # A room display is the new current output; it supersedes any
            # lingering one-off message. Walking to a new peaceful room also
            # retires a finished fight's box.
            self.current_room = room
            self.latest_message = ""
            self.cards.append(room)
            emitted.append(room)
            if name == "move" and not self.combat_active:
                self.combat_lines, self.combat_result = [], None
        elif not is_combat_result:
            # A non-room, non-combat reply (examine, track, a shop list) is a
            # transient MUD message, shown live on the dashboard but not kept as
            # a Feed card. Line structure is preserved so a list stays a list.
            self.latest_message = self._clean(event.get("result"))[:600]
        if combat_card is not None:
            emitted.append(combat_card)
        return emitted

    def _absorb_combat(self, text: str) -> Card | None:
        """Track a fight the week0 way: windowed and line-matched, not sticky.

        A result counts as combat only for the lines that match
        :data:`COMBAT_LINE_RE`, so a reconnect menu or an error can never leak
        into the box. A result with no combat lines and no death ENDS an
        ongoing fight (disconnect, fled, moved on) rather than leaving it stuck
        on. Returns a combat :class:`Card` for the Feed when the fight ends
        with a known outcome.
        """
        lines = [ln.strip() for ln in text.splitlines()
                 if ln.strip() and not PROMPT_LINE_RE.match(ln.strip())]
        combat = [ln for ln in lines if COMBAT_LINE_RE.search(ln)]
        died = any("you are dead" in ln.lower() for ln in lines)
        if not combat and not died:
            if self.combat_active:
                # The fight stopped without a clean outcome we saw: retire an
                # unresolved box so stale or disconnect text cannot linger.
                self.combat_active = False
                if self.combat_result is None:
                    self.combat_lines = []
            return None
        if not self.combat_active and self.combat_result is None:
            self.combat_lines = []                      # a fresh fight
        self.combat_active = True
        self.combat_result = None
        self.combat_lines.extend(combat)
        del self.combat_lines[:-24]
        kill = next((m for m in (COMBAT_KILL_RE.search(ln) for ln in lines) if m),
                    None)
        if kill:
            victim = re.sub(r"^[Tt]he ", "", kill.group(1).strip())
            self.combat_active = False
            self.combat_result = f"Victory over the {victim}"
        elif died:
            self.combat_active = False
            self.combat_result = "You were defeated"
        if not self.combat_active and self.combat_result:
            card = Card(kind="combat", title=self.combat_result,
                        body="\n".join(self.combat_lines))
            self.cards.append(card)
            return card
        return None

    def _room_card(self, result) -> Card | None:
        """Parse a look/move result into a RoomCard: title, description, exits."""
        text = strip_ansi(result)
        exits_match = EXITS_RE.search(text)
        exits = exits_match.group(1).split() if exits_match else []
        lines = [ln.rstrip() for ln in text.splitlines()]
        # Drop the game-prompt telemetry line and the exits line from the body.
        body_lines: list[str] = []
        title = ""
        for line in lines:
            if not line.strip():
                continue
            if PROMPT_LINE_RE.match(line) or EXITS_RE.match(line.strip()):
                continue
            if not title:
                title = line.strip()
            else:
                body_lines.append(line.strip())
        if not title:
            return None
        return RoomCard(title, " ".join(body_lines), exits)

    @staticmethod
    def _clean(text) -> str:
        """Strip ANSI and the game-prompt telemetry line, but KEEP the line
        structure. Tables, numbered lists, and paragraphs stay legible instead
        of being mashed into one run-on line. Trailing space per line goes, and
        runs of blank lines are squeezed to one."""
        lines = []
        for line in strip_ansi(text).splitlines():
            if PROMPT_LINE_RE.match(line.strip()):
                continue
            lines.append(line.rstrip())
        out = "\n".join(lines).strip("\n")
        return re.sub(r"\n{3,}", "\n\n", out)

    def __str__(self) -> str:
        return (f"<Presenter cards={len(self.cards)} "
                f"room={self.current_room and self.current_room.title!r}>")

    __repr__ = __str__
