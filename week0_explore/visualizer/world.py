"""True-world knowledge for the visualizer (NOT for the playing agent).

Parses the tbaMUD world files the server actually runs (lib/world/wld/*.wld)
into a room graph, and localizes the agent on it by replaying the session
transcript: each observed room title + each movement narrows a belief set of
candidate vnums until the position is exact. This is what lets the map keep
five same-titled "Main Street" segments apart — identity is the vnum, not the
title.
"""
import glob
import os
import re

DIR_NAMES = ["north", "east", "south", "west", "up", "down"]

VNUM_RE = re.compile(r"^#(\d+)")
DOOR_RE = re.compile(r"^D([0-5])")
EXIT_INFO_RE = re.compile(r"^(-?\d+)\s+(-?\d+)\s+(-?\d+)")


def parse_wld_dir(path):
    """{vnum: {"title": str, "exits": {dirname: to_vnum}}} for all .wld files."""
    rooms = {}
    for f in sorted(glob.glob(os.path.join(path, "*.wld"))):
        rooms.update(parse_wld_file(f))
    return rooms


def parse_wld_file(path):
    rooms = {}
    with open(path, encoding="latin-1") as fh:
        lines = fh.read().split("\n")
    i, n = 0, len(lines)
    while i < n:
        m = VNUM_RE.match(lines[i])
        if not m:
            i += 1
            continue
        vnum = int(m.group(1))
        i += 1
        title = lines[i].rstrip("~").strip() if i < n else ""
        i += 1
        while i < n and not lines[i].endswith("~"):   # room description
            i += 1
        i += 1                                        # past the "~"
        i += 1                                        # zone/flags/sector line
        exits = {}
        while i < n:
            line = lines[i].strip()
            if line == "S" or VNUM_RE.match(line):
                break
            dm = DOOR_RE.match(line)
            if dm:
                d = int(dm.group(1))
                i += 1
                for _ in range(2):                    # exit desc ~, keywords ~
                    while i < n and not lines[i].endswith("~"):
                        i += 1
                    i += 1
                em = EXIT_INFO_RE.match(lines[i].strip()) if i < n else None
                if em:
                    to = int(em.group(3))
                    if to >= 0:
                        exits[DIR_NAMES[d]] = to
                i += 1
            else:
                i += 1
        rooms[vnum] = {"title": title, "exits": exits}
        if i < n and lines[i].strip() == "S":
            i += 1
    return rooms


# --- localization over the transcript ----------------------------------------

PROMPT_RE = re.compile(r"\d+H \d+M \d+V[^\n]*?> ")
SENT_RE = re.compile(r"^\[SENT\] (.*)$")
EXITS_LINE_RE = re.compile(r"^\[ Exits: ([^\]]+)\]")
DIR_WORDS = {"n": "north", "s": "south", "e": "east", "w": "west",
             "u": "up", "d": "down"}
for _d in DIR_NAMES:
    DIR_WORDS[_d] = _d


class Localizer:
    """Replays the cleaned transcript stream and tracks where the agent is.

    Belief = set of candidate vnums. A room display filters it by title; a
    movement advances it along graph edges. When it collapses to one room we
    know the position exactly and record visited rooms + walked edges; a
    short history lets us backfill the steps taken while ambiguous.
    """

    def __init__(self, graph):
        self.graph = graph
        self.by_title = {}
        for v, r in graph.items():
            self.by_title.setdefault(r["title"], set()).add(v)
        self.belief = set()
        self.visited = set()          # vnums seen while position was exact
        self.edges = {}               # (from_vnum, dir) -> to_vnum, walked
        self.trail = []               # recent exact moves: (dir, from, to)
        self.position = None          # exact vnum or None
        self.hazards = {}             # vnum -> [notes] (deaths, darkness)
        self._pending_move = None
        self._ambig_steps = []        # (dir|None, title) while belief > 1
        self._linebuf = ""
        self._recent = []

    # -- feeding the transcript
    def feed(self, chunk):
        self._linebuf += chunk
        self._linebuf = PROMPT_RE.sub("\n", self._linebuf)
        while "\n" in self._linebuf:
            line, self._linebuf = self._linebuf.split("\n", 1)
            self._line(line.rstrip())

    def _line(self, line):
        self._recent.append(line)
        del self._recent[:-30]
        m = SENT_RE.match(line)
        if m:
            word = m.group(1).strip().lower().split(" ")[0]
            self._pending_move = DIR_WORDS.get(word)
            return
        if "It is pitch black" in line:
            if self.position is not None and self._pending_move:
                self.hazards.setdefault(self.position, []).append(
                    "darkness through %s" % self._pending_move)
            self._jump(set())        # position unknown until next room display
            return
        if "You are dead!" in line and self.position is not None:
            self.hazards.setdefault(self.position, []).append(
                "a death occurred here")
        m = EXITS_LINE_RE.match(line.strip())
        if m:
            self._room_observed(m.group(1).strip())

    def _room_observed(self, exits_str):
        # title: walk back to the line after the last blank/[SENT] boundary
        idx = len(self._recent) - 2
        boundary = -1
        for i in range(idx, -1, -1):
            l = self._recent[i]
            if not l.strip() or l.startswith("[SENT]"):
                boundary = i
                break
        title = None
        for i in range(boundary + 1, idx + 1):
            if self._recent[i].strip():
                title = self._recent[i].strip()
                break
        if not title or len(title) > 60 or title[-1] in ".!?,;:'\"":
            self._pending_move = None
            return
        cands = self.by_title.get(title, set())
        move = self._pending_move
        self._pending_move = None

        if move and self.belief:
            stepped = {self.graph[c]["exits"].get(move) for c in self.belief}
            stepped = {v for v in stepped if v is not None} & cands
            new = stepped if stepped else set(cands)
            if not stepped:
                move = None          # graph disagrees: treat as teleport
        else:
            if self.belief and not move:
                new = (self.belief & cands) or set(cands)  # a `look`
                if self.belief & cands:
                    self._resolve(new, None, title)
                    return
            new = set(cands)
        self._resolve(new, move, title)

    def _resolve(self, new, move, title):
        prev = self.position
        was_ambiguous = len(self.belief) != 1
        self.belief = new
        if len(new) == 1:
            v = next(iter(new))
            self.position = v
            self.visited.add(v)
            if move and prev is not None and not was_ambiguous:
                self.edges[(prev, move)] = v
                self.trail.append((move, prev, v))
                del self.trail[:-15]
            elif self._ambig_steps:
                self._backfill(v)
            self._ambig_steps = []
        else:
            self.position = None
            self._ambig_steps.append((move, title))
            del self._ambig_steps[:-8]

    def _backfill(self, v):
        """Walk the ambiguous step chain backwards from a now-known room."""
        cur = v
        for move, _title in reversed(self._ambig_steps):
            if not move:
                break
            preds = [p for p, r in self.graph.items()
                     if r["exits"].get(move) == cur]
            if len(preds) != 1:
                break
            self.visited.add(preds[0])
            self.edges[(preds[0], move)] = cur
            self.trail.append((move, preds[0], cur))
            cur = preds[0]
        del self.trail[:-15]

    def _jump(self, belief):
        self.belief = belief
        self.position = None
        self._ambig_steps = []


class WorldTracker:
    """Incrementally follows a transcript file with a Localizer."""

    def __init__(self, wld_dir, transcript_path):
        self.graph = parse_wld_dir(wld_dir)
        self.transcript = transcript_path
        self.loc = Localizer(self.graph)
        self._offset = 0

    def update(self):
        try:
            size = os.path.getsize(self.transcript)
        except OSError:                              # deleted: forget the replay
            if self._offset:
                self.loc = Localizer(self.graph)
                self._offset = 0
            return
        if size < self._offset:                      # truncated: start over
            self.loc = Localizer(self.graph)
            self._offset = 0
        if size == self._offset:
            return
        with open(self.transcript, encoding="utf-8", errors="replace") as f:
            f.seek(self._offset)
            self.loc.feed(f.read())
            self._offset = f.tell()
