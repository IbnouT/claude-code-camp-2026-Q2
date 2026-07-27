"""World: the MUD's own room graph, and a map laid out from it.

The log says where the agent went by quoting what the game printed. That is not enough
to draw a path, because ROOM TITLES DO NOT IDENTIFY ROOMS. Measured on this world's own
files: 1,878 rooms, 241 titles shared by more than one room, and one title shared by
forty-one. A trail built from titles folds distinct places together and invents movements
that never happened.

Those counts are CASE-INSENSITIVE, which is the method rather than an aside: two rooms
whose titles differ only in case are the same title to a reader, and matching here folds
case for the same reason. Counted case-sensitively the figures are 240 and 40.

The world's own files do identify them. Each room has a vnum and typed exits, so a title
plus the exit taken plus the room the agent was in resolves to exactly one destination.
That is the same correlation week 0 arrived at, reimplemented here rather than imported:
these are DATA FILES, read the way the log is read, so the viewer still imports nothing.

What this is not: a general MUD library. It parses what a path needs, room numbers,
titles, and exits, and ignores everything else in the format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .html import strip_ansi

#: Direction slots in the order CircleMUD writes them, so `D0` is north.
DIRECTIONS = ("north", "east", "south", "west", "up", "down")

#: How the game names a direction in a command, mapped to its slot.
BY_NAME = {name: index for index, name in enumerate(DIRECTIONS)}
BY_NAME.update({"n": 0, "e": 1, "s": 2, "w": 3, "u": 4, "d": 5})

#: Where the world files live relative to the repository, and the environment variable
#: that overrides it. Absent, the spatial lens says the world is not available rather
#: than guessing a path or failing.
WORLD_ENV = "BOUKENSHA_WORLD"
WORLD_HINT = Path("week0_explore/circlemud-world-parser/assets/wld")

_ROOM = re.compile(r"^#(\d+)\s*$")
_EXIT = re.compile(r"^D([0-5])\s*$")
#: An exit's numbers line: flags, key vnum, destination. Destination -1 means nowhere.
_TARGET = re.compile(r"^(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*$")


@dataclass
class Room:
    """One room: its number, its name, and where its exits lead."""

    vnum: int
    title: str
    zone: int = 0
    exits: dict[int, int] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"<Room {self.vnum} title={self.title!r} exits={len(self.exits)}>"

    __repr__ = __str__


def find_world(start: str | Path | None = None) -> Path | None:
    """Where the world files are, or None.

    Checked rather than assumed, because a viewer reading someone else's logs may have
    no world at all, and the spatial lens saying so is better than a stack trace.
    """
    import os

    override = os.environ.get(WORLD_ENV)
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.is_dir() else None
    here = Path(start).resolve() if start else Path.cwd().resolve()
    for base in (here, *here.parents):
        candidate = base / WORLD_HINT
        if candidate.is_dir():
            return candidate
    return None


def load(directory: str | Path | None = None) -> dict[int, Room]:
    """Every room in the world, by vnum. An unreadable file is skipped, not fatal."""
    target = Path(directory) if directory else find_world()
    if target is None or not Path(target).is_dir():
        return {}
    rooms: dict[int, Room] = {}
    for path in sorted(Path(target).glob("*.wld")):
        try:
            rooms.update(_parse(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return rooms


def _parse(text: str) -> dict[int, Room]:
    """One world file to rooms.

    A hand-rolled scan rather than a grammar, because the format is line-oriented and
    only three of its constructs matter here. Anything unrecognised is skipped, so a
    zone using a feature this ignores still yields its rooms and exits.
    """
    rooms: dict[int, Room] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = _ROOM.match(lines[index])
        index += 1
        if not match:
            continue
        vnum = int(match.group(1))
        title = ""
        if index < len(lines):
            title = lines[index].rstrip("~").strip()
            index += 1
        # Skip the description, which ends on a line that is just a tilde.
        while index < len(lines) and lines[index].strip() != "~":
            index += 1
        index += 1
        zone = 0
        if index < len(lines):
            parts = lines[index].split()
            if parts and parts[0].lstrip("-").isdigit():
                zone = int(parts[0])
            index += 1
        room = Room(vnum=vnum, title=title, zone=zone)
        # Exits and extras, until the room's terminating S.
        while index < len(lines):
            line = lines[index].strip()
            if line == "S":
                index += 1
                break
            exit_match = _EXIT.match(line)
            if not exit_match:
                index += 1
                continue
            slot = int(exit_match.group(1))
            index += 1
            # Two tilde-terminated blocks, the description and the keyword, then the
            # numbers line carrying the destination.
            seen = 0
            while index < len(lines) and seen < 2:
                if lines[index].strip().endswith("~"):
                    seen += 1
                index += 1
            while index < len(lines):
                target = _TARGET.match(lines[index].strip())
                index += 1
                if target:
                    destination = int(target.group(3))
                    if destination >= 0:
                        room.exits[slot] = destination
                    break
        rooms[vnum] = room
    return rooms


@dataclass
class Step:
    """One resolved move: where the agent was, what it did, where it ended."""

    order: int
    turn: int
    direction: str | None
    vnum: int | None
    title: str
    blocked: bool = False
    #: True when the title matched more than one room and the exit resolved it. Worth
    #: reporting: it is the whole reason this module exists.
    disambiguated: bool = False

    def __str__(self) -> str:
        return f"<Step {self.order} turn={self.turn} vnum={self.vnum} {self.title!r}>"

    __repr__ = __str__


def trail(moves: list[tuple[int, str | None, str, bool]],
          rooms: dict[int, Room]) -> list[Step]:
    """Resolve a sequence of (turn, direction, title, ok) into identified rooms.

    The correlation, in one sentence: from a known room, taking a known exit lands in
    exactly one room, so a title that matches several is decided by where the agent came
    from. Starting position is found by title, and a title matching many rooms with no
    prior position stays unresolved rather than picking one.

    A blocked move keeps the agent where it was. That matters for the map, where a
    blocked exit is a wall the agent kept walking into.
    """
    by_title: dict[str, list[int]] = {}
    for room in rooms.values():
        by_title.setdefault(strip_ansi(room.title).lower(), []).append(room.vnum)

    steps: list[Step] = []
    current: int | None = None
    for order, (turn, direction, title, ok) in enumerate(moves, start=1):
        # MUD titles arrive wrapped in colour codes, so a raw comparison against the
        # world files matches nothing at all. Stripped here rather than at the call
        # site, because every caller reads the same coloured output.
        clean = strip_ansi(title).strip()
        key = clean.lower()
        if not ok:
            steps.append(Step(order=order, turn=turn, direction=direction,
                              vnum=current, title=clean or "blocked", blocked=True))
            continue
        candidates = by_title.get(key, [])
        resolved: int | None = None
        ambiguous = len(candidates) > 1
        slot = BY_NAME.get((direction or "").lower())
        if current is not None and slot is not None:
            # From here, that exit leads to exactly one room. Trust it over the title.
            destination = rooms[current].exits.get(slot) if current in rooms else None
            if destination is not None:
                resolved = destination
        if resolved is None and len(candidates) == 1:
            resolved = candidates[0]
        if resolved is None and candidates and current is not None:
            # Prefer a candidate the current room actually connects to.
            reachable = set(rooms[current].exits.values()) if current in rooms else set()
            connected = [v for v in candidates if v in reachable]
            if len(connected) == 1:
                resolved = connected[0]
        current = resolved if resolved is not None else current
        steps.append(Step(order=order, turn=turn, direction=direction, vnum=resolved,
                          title=clean or (rooms[resolved].title if resolved in rooms
                                          else "unknown"),
                          disambiguated=bool(ambiguous and resolved is not None)))
    return steps


def layout(steps: list[Step], rooms: dict[int, Room]) -> dict[int, tuple[int, int]]:
    """Place the visited rooms on a grid by walking the moves.

    A MUD's exits are compass directions, so the map draws itself: start anywhere and
    step north, east, south, west as the trail says. Up and down do not move the point,
    they stack, which is why two rooms can land on one square. That is a property of the
    world rather than a flaw here, so overlaps are nudged rather than hidden.
    """
    grid: dict[int, tuple[int, int]] = {}
    taken: dict[tuple[int, int], int] = {}
    x = y = 0
    for step in steps:
        if step.vnum is None:
            continue
        if step.vnum in grid:
            x, y = grid[step.vnum]
            continue
        slot = BY_NAME.get((step.direction or "").lower())
        if slot == 0:
            y -= 1
        elif slot == 1:
            x += 1
        elif slot == 2:
            y += 1
        elif slot == 3:
            x -= 1
        spot = (x, y)
        nudge = 0
        while spot in taken and taken[spot] != step.vnum:
            nudge += 1
            spot = (x + nudge, y)
        grid[step.vnum] = spot
        taken[spot] = step.vnum
        x, y = spot
    return grid
