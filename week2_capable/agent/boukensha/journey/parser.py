"""Journey: turn raw MUD tool output into structured player-journey state.

``JourneyParser`` consumes the agent's tool activity (``tool_call`` /
``tool_result`` / ``turn`` events from ``Logger.subscribe``) and accumulates a
``JourneyState``: the rooms seen, their links, the agent's position and trail,
vitals and their history, character stats, and notable events (kills, level-ups,
deaths). This is the data layer of the journey observatory; panels read it, and
the findings heuristics build on it.

Framework-free by design (no Textual import), so it is unit-testable with plain
text fixtures. The line rules are lifted from week0's proven CircleMUD parser
(``play-mud``'s ``mud_session.py``), not invented: vitals prompt lines like
``90H 100M 92V >``, room headers followed by ``[ Exits: n e ]``, kill/XP/level/
death lines. Every miss is a no-op, never an exception: a MUD that emits
different text (the toy dummy server) simply accumulates nothing, and panels
show honest empty states.

Two structural advantages over the week0 raw-telnet parser:

- the MCP ``tool_call`` args carry intent (``move(direction="north")``), so a
  link's direction is read from structure, never guessed from prose, and
- each ``tool_result`` is one complete reply, so a room boundary is the result
  itself, with no stream walk-back.

Room identity uses the week0 title+exits heuristic: same-titled rooms with
different exit sets get a numbered suffix. This is honestly approximate (a real
MUD has same-titled rooms), and vnum-true identity from the MUD's ``.wld`` world
files is deferred to week 2 with the world map (see the journal's Explore later).
"""

from __future__ import annotations

import re
from typing import Any

from ..tool_result import view_tool_result

# Line rules, verbatim from week0's mud_session.py (verified against real
# tbaMUD transcripts there).
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b[()][0-9A-B]|\x1b[=>]")
VITALS_RE = re.compile(r"(\d+)H (\d+)M (\d+)V")
EXITS_RE = re.compile(r"^\[ Exits: ([^\]]+)\]")
SCORE_RANK_RE = re.compile(r"This ranks you as (.+) \(level (\d+)\)")
SCORE_XP_RE = re.compile(r"You have (\d+) exp, (\d+) gold")
SCORE_TNL_RE = re.compile(r"You need (\d+) exp to reach your next level")
SCORE_MAX_RE = re.compile(
    r"You have \d+\((\d+)\) hit, \d+\((\d+)\) mana and \d+\((\d+)\) movement")
# Condition lines from the score/check output: the player's stance and needs.
POSITION_RE = re.compile(r"You are (standing|sitting|resting|sleeping|fighting)")
HUNGRY_RE = re.compile(r"You are hungry")
THIRSTY_RE = re.compile(r"You are thirsty")
KILL_RE = re.compile(r"^(.+) is dead!\s*R\.I\.P\.")
EXP_RE = re.compile(r"You receive (\d+) experience|You receive your share of experience")
LEVEL_RE = re.compile(r"You rise a level!")
DEATH_RE = re.compile(r"^You are dead!")
NOWAY_RE = re.compile(r"Alas, you cannot go that way")
DARK_RE = re.compile(r"It is pitch black")

#: Tools whose result describes the current room.
ROOM_TOOLS = frozenset({"look", "move"})
#: How many vitals/xp/gold samples the histories keep (sparkline width).
HISTORY_LIMIT = 60

# -- findings thresholds: named judgment calls, tuned by eye, tested by fixture.
#: Looks with no room change or new info within the recent window reads as
#: confusion: a player re-reading the same description is lost.
CONFUSION_LOOKS = 3
#: The recent-call window those looks are counted in.
CONFUSION_WINDOW = 6
#: The same (room, direction) rejected this many times is a blocker, not a typo.
BLOCKED_REPEATS = 2
#: Trail steps examined for grinding; touching few rooms in this many steps
#: means the session is looping, not progressing.
GRINDING_WINDOW = 10
#: "Few rooms" for the grinding window.
GRINDING_DISTINCT_ROOMS = 2
#: Losing at most this fraction of max HP in a won fight reads overpowered.
OVERPOWERED_HP_FRACTION = 0.05
#: Losing at least this fraction (or dying) reads underpowered.
UNDERPOWERED_HP_FRACTION = 0.40


class JourneyState:
    """The accumulated journey: what a panel reads, what a finding is derived from."""

    def __init__(self) -> None:
        #: {key: {"title", "exits": [..], "links": {dir: key}, "hazards": [..],
        #:  "visits": int}}
        self.rooms: dict[str, dict[str, Any]] = {}
        self.position: str | None = None
        #: [(turn, direction, from_key, to_key)]
        self.trail: list[tuple[int, str | None, str | None, str]] = []
        self.vitals: dict[str, int | None] = {
            "hp": None, "mana": None, "moves": None,
            "max_hp": None, "max_mana": None, "max_moves": None,
        }
        self.vitals_history: list[int] = []
        self.xp_history: list[int] = []
        self.gold_history: list[int] = []
        self.char: dict[str, Any] = {
            "level": None, "xp": None, "xp_to_next": None, "gold": None,
            "rank": None,
        }
        #: Condition read from the score: stance and needs (shown in the header).
        self.status: dict[str, Any] = {
            "stance": None, "hungry": False, "thirsty": False}
        #: [(turn, text)] kills, level-ups, deaths.
        self.events: list[tuple[int, str]] = []
        self.deaths = 0
        self.turn = 0

    @property
    def frontier(self) -> list[tuple[str, str]]:
        """Untried exits: ``(room_key, direction)`` with no known link."""
        out = []
        for key, room in self.rooms.items():
            for direction in room["exits"]:
                if direction not in room["links"]:
                    out.append((key, direction))
        return out

    def __str__(self) -> str:
        return (
            f"<JourneyState rooms={len(self.rooms)} position={self.position!r} "
            f"deaths={self.deaths} turn={self.turn}>"
        )

    __repr__ = __str__


class JourneyParser:
    """Feed me the logger's events; read the :class:`JourneyState` back.

    Wire as a second ``logger.subscribe`` callback via :meth:`on_event` (the
    subscriber guard in the Logger means a bug here can never crash a turn), or
    call the ``on_*`` methods directly in tests. NOT thread-safe by itself: the
    TUI posts events to its app thread and mutates there, per its thread rule.
    """

    def __init__(self) -> None:
        self.state = JourneyState()
        self._pending: dict[str, dict[str, Any]] = {}
        #: Recent calls: {"name", "new_info"} for the confusion window.
        self._recent_calls: list[dict[str, Any]] = []
        #: {(room, direction): fail count} for the blocked finding.
        self._blocked: dict[tuple[str | None, str], int] = {}
        #: Derived over/underpowered findings, appended per combat bracket.
        self._combat_findings: list[dict[str, Any]] = []
        self._hp_before_fight: int | None = None

    # -- event entry points --------------------------------------------------

    def on_event(self, event: dict[str, Any]) -> None:
        phase = event.get("phase")
        if phase == "turn":
            self.state.turn = int(event.get("n") or 0)
        elif phase == "tool_call":
            self.on_tool_call(event.get("name"), event.get("args"), event.get("id"))
        elif phase == "tool_result":
            self.on_tool_result(event.get("name"), event.get("result"),
                                event.get("tool_use_id"))

    def on_tool_call(self, name: Any, args: Any, call_id: Any = None) -> None:
        # Remember the call's intent so its result can be interpreted with
        # structured context (the move direction, the check kind). The MCP
        # host's agent-side prefix (tbamud__look) is stripped so dispatch works
        # whatever prefix the config chose.
        bare = str(name or "").split("__")[-1]
        self._pending[str(call_id or name)] = {
            "name": bare, "args": dict(args or {}),
        }

    def on_tool_result(self, name: Any, result: Any, call_id: Any = None) -> None:
        call = self._pending.pop(str(call_id or name), None) or {
            "name": str(name or "").split("__")[-1], "args": {},
        }
        view = view_tool_result(result)
        text = ANSI_RE.sub("", view.text)
        hp_before = self.state.vitals["hp"]
        position_before = self.state.position
        if view.is_error:
            self._recent_calls.append({
                "name": call["name"],
                "new_info": False,
            })
            del self._recent_calls[:-CONFUSION_WINDOW]
            return
        self._scan_lines(text)
        if call["name"] in ROOM_TOOLS:
            self._parse_room(text, call)
        # Finding trackers.
        if call["name"] == "move" and NOWAY_RE.search(text):
            direction = str(call["args"].get("direction") or "?")
            key = (position_before, direction)
            self._blocked[key] = self._blocked.get(key, 0) + 1
        self._recent_calls.append({
            "name": call["name"],
            "new_info": self.state.position != position_before,
        })
        del self._recent_calls[:-CONFUSION_WINDOW]
        if call["name"] in ("attack", "skill_strike") and self._hp_before_fight is None:
            self._hp_before_fight = hp_before
        if KILL_RE.search(text) and self._hp_before_fight is not None:
            self._close_fight(won=True)
        elif DEATH_RE.search(text):
            self._close_fight(won=False)

    def _close_fight(self, won: bool) -> None:
        """End a combat bracket; classify over/underpowered from the HP delta."""
        before, self._hp_before_fight = self._hp_before_fight, None
        after = self.state.vitals["hp"]
        max_hp = self.state.vitals["max_hp"]
        if not won:
            self._combat_findings.append({
                "kind": "underpowered", "room": self.state.position,
                "turn": self.state.turn, "detail": "died in combat"})
            return
        if before is None or after is None or not max_hp:
            return
        lost = (before - after) / max_hp
        if lost <= OVERPOWERED_HP_FRACTION:
            self._combat_findings.append({
                "kind": "overpowered", "room": self.state.position,
                "turn": self.state.turn,
                "detail": f"won losing {round(lost * 100)}% HP"})
        elif lost >= UNDERPOWERED_HP_FRACTION:
            self._combat_findings.append({
                "kind": "underpowered", "room": self.state.position,
                "turn": self.state.turn,
                "detail": f"won but lost {round(lost * 100)}% HP"})

    # -- line-level capture ---------------------------------------------------

    def _scan_lines(self, text: str) -> None:
        """Capture vitals, score facts, and notable events from any result."""
        state = self.state
        for line in text.splitlines():
            line = line.strip()
            vit = VITALS_RE.search(line)
            if vit and line.endswith(">"):
                state.vitals["hp"] = int(vit.group(1))
                state.vitals["mana"] = int(vit.group(2))
                state.vitals["moves"] = int(vit.group(3))
                self._sample(state.vitals_history, int(vit.group(1)))
            m = SCORE_MAX_RE.search(line)
            if m:
                state.vitals["max_hp"] = int(m.group(1))
                state.vitals["max_mana"] = int(m.group(2))
                state.vitals["max_moves"] = int(m.group(3))
                # A fresh score reports current needs, so reset them here and
                # let the condition lines below in the same block set them.
                state.status["hungry"] = False
                state.status["thirsty"] = False
            m = POSITION_RE.search(line)
            if m:
                state.status["stance"] = m.group(1)
            if HUNGRY_RE.search(line):
                state.status["hungry"] = True
            if THIRSTY_RE.search(line):
                state.status["thirsty"] = True
            m = SCORE_RANK_RE.search(line)
            if m:
                state.char["rank"] = m.group(1)
                state.char["level"] = int(m.group(2))
            m = SCORE_XP_RE.search(line)
            if m:
                state.char["xp"] = int(m.group(1))
                state.char["gold"] = int(m.group(2))
                self._sample(state.xp_history, int(m.group(1)))
                self._sample(state.gold_history, int(m.group(2)))
            m = SCORE_TNL_RE.search(line)
            if m:
                state.char["xp_to_next"] = int(m.group(1))
            m = KILL_RE.match(line)
            if m:
                state.events.append((state.turn, f"killed {m.group(1)}"))
            if LEVEL_RE.search(line):
                state.events.append((state.turn, "level up"))
            if DEATH_RE.match(line):
                state.deaths += 1
                state.events.append((state.turn, "DIED"))
                if state.position and state.position in state.rooms:
                    hazards = state.rooms[state.position]["hazards"]
                    if "death" not in hazards:
                        hazards.append("death")

    # -- room tracking --------------------------------------------------------

    def _parse_room(self, text: str, call: dict[str, Any]) -> None:
        """A look/move result describes a room: title, exits, and a link."""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        title = None
        exits: list[str] = []
        for i, line in enumerate(lines):
            m = EXITS_RE.match(line)
            if m:
                exits = m.group(1).split()
                # The room title is the first non-prompt line of the block.
                for candidate in lines[:i]:
                    if not VITALS_RE.search(candidate):
                        title = candidate
                        break
                break
        if title is None:
            # A failed move never changes the room.
            if call["name"] == "move" and NOWAY_RE.search(text):
                return
            return
        direction = None
        if call["name"] == "move":
            direction = str(call["args"].get("direction") or "") or None
        key = self._room_key(title, exits)
        room = self.state.rooms.setdefault(
            key, {"title": title, "exits": exits, "links": {}, "hazards": [],
                  "visits": 0})
        room["visits"] += 1
        room["exits"] = exits or room["exits"]
        if DARK_RE.search(text) and "dark" not in room["hazards"]:
            room["hazards"].append("dark")

        previous = self.state.position
        if direction and previous and previous in self.state.rooms:
            self.state.rooms[previous]["links"][direction] = key
        self.state.position = key
        if key != previous or direction:
            self.state.trail.append((self.state.turn, direction, previous, key))

    def _room_key(self, title: str, exits: list[str]) -> str:
        """Same-titled rooms with different exits get a numbered suffix, the
        week0 disambiguation rule."""
        existing = self.state.rooms.get(title)
        if existing is None or existing["exits"] == exits or not exits:
            return title
        n = 2
        while True:
            key = f"{title} ({n})"
            room = self.state.rooms.get(key)
            if room is None or room["exits"] == exits:
                return key
            n += 1

    @staticmethod
    def _sample(history: list[int], value: int) -> None:
        history.append(value)
        del history[:-HISTORY_LIMIT]

    # -- findings derivation (the journey insight engine) --------------------

    def derive_findings(self) -> list[dict[str, Any]]:
        """Derive journey findings from the accumulated state.

        Windowed and re-evaluated, not one-shot: call after any event batch.
        Each finding: {kind, room, turn, detail}. Kinds: confusion, blocked,
        bored, overpowered, underpowered, death.
        """
        state = self.state
        findings: list[dict[str, Any]] = []
        recent = self._recent_calls[-CONFUSION_WINDOW:]
        looks = [c for c in recent if c["name"] == "look" and not c["new_info"]]
        if len(looks) >= CONFUSION_LOOKS:
            findings.append({"kind": "confusion", "room": state.position,
                             "turn": state.turn,
                             "detail": f"{len(looks)} looks, nothing new"})
        for (room, direction), n in self._blocked.items():
            if n >= BLOCKED_REPEATS:
                findings.append({"kind": "blocked", "room": room,
                                 "turn": state.turn,
                                 "detail": f"{direction} failed x{n}"})
        steps = state.trail[-GRINDING_WINDOW:]
        if len(steps) >= GRINDING_WINDOW:
            rooms = {s[3] for s in steps}
            if len(rooms) <= GRINDING_DISTINCT_ROOMS:
                findings.append({"kind": "bored", "room": state.position,
                                 "turn": state.turn,
                                 "detail": f"{len(steps)} steps in {len(rooms)} rooms"})
        findings.extend(self._combat_findings)
        for turn, text in state.events:
            if text == "DIED":
                findings.append({"kind": "death", "room": state.position,
                                 "turn": turn, "detail": "died here"})
        return findings

    def __str__(self) -> str:
        return f"<JourneyParser {self.state}>"

    __repr__ = __str__
