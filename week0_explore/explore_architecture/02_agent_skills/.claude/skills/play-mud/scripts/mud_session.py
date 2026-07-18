#!/usr/bin/env python3
"""Persistent MUD session manager.

Owns a single telnet connection to the MUD and exposes it through a small
control socket, so every `cmd` call talks to the SAME live game session
instead of opening a new connection per command.

Usage:
    mud_session.py start              # connect + log in, then daemonize
    mud_session.py cmd "look"         # send one command, print the response
    mud_session.py recv [--wait N]    # drain async output (combat, chat...)
    mud_session.py status             # is the session alive? last prompt? goals?
    mud_session.py log [-n N]         # tail the full session transcript
    mud_session.py stop               # quit the game and shut down
    mud_session.py goal "..."         # add a free-form note/goal to data/player.md
    mud_session.py memory             # print data/player.md and data/world.md
    mud_session.py plan set "..."     # set the long-term goal of the plan
    mud_session.py plan add "..." [--check "level>=7"]   # append a subtask
    mud_session.py plan done          # mark current subtask done, advance
    mud_session.py plan show          # plan with live condition checks
    mud_session.py persona "..."      # set the play style (persona) to apply
    mud_session.py find <terms>       # search everything the memory knows

Memory: the daemon auto-maintains data/player.md (vitals, character, events,
goals) and data/world.md (room map) in the directory the session was started
from, updating them in real time as game output arrives.

Connection settings can be overridden with env vars:
    MUD_HOST, MUD_PORT, MUD_USER, MUD_PASS, MUD_SESSION_DIR, MUD_MEMORY_DIR
"""
import argparse
import codecs
import json
import os
import re
import select
import socket
import sys
import time

HOST = os.environ.get("MUD_HOST", "localhost")
PORT = int(os.environ.get("MUD_PORT", "4000"))
USER = os.environ.get("MUD_USER", "dummy")
PASSWORD = os.environ.get("MUD_PASS", "helloworld")

SESSION_DIR = os.path.expanduser(
    os.environ.get("MUD_SESSION_DIR", "~/.play_mud/%s_%d" % (HOST, PORT)))
SOCK_PATH = os.path.join(SESSION_DIR, "control.sock")
TRANSCRIPT = os.path.join(SESSION_DIR, "transcript.log")
PIDFILE = os.path.join(SESSION_DIR, "daemon.pid")
DAEMON_LOG = os.path.join(SESSION_DIR, "daemon.log")

# --- telnet protocol bytes ---
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b[()][0-9A-B]|\x1b[=>]")
# In-game prompt, e.g. "90H 100M 92V (news) > ". Fallback: buffer ends "> ".
GAME_PROMPT_RE = re.compile(r"\d+H \d+M \d+V[^\n]*>\s?$")
# CircleMUD/tbaMUD pager prompts for long output.
PAGER_RE = re.compile(
    r"(\*\*\* Press return \*\*\*|\[ Return to continue[^\]\n]*\])\s*$",
    re.IGNORECASE)


class SessionError(Exception):
    pass


# --- memory -----------------------------------------------------------------
# The daemon watches the whole game stream and maintains two markdown files in
# the directory the session was started from. Updates happen as output arrives
# so the playing agent never has to remember to take notes.

MEM_DIR = os.path.abspath(os.environ.get("MUD_MEMORY_DIR", "data"))
PLAYER_MD = os.path.join(MEM_DIR, "player.md")
WORLD_MD = os.path.join(MEM_DIR, "world.md")
MEM_STATE = os.path.join(MEM_DIR, ".mud_memory.json")

GOALS_HEADER = "## Goals & notes (edit freely — this section is never auto-overwritten)"
AUTO_MARKER = ("<!-- AUTO — everything below is rewritten in real time by "
               "mud_session.py; edits below this line are lost -->")
DEFAULT_GOALS = ('- (no notes yet — add lines here, or run: '
                 'mud_session.py goal "...insight...")')

# The plan (goal, ordered subtasks, persona) lives in its own file, owned by
# the CLI subcommands; the daemon only reads it, so there is no write conflict.
PLAN_FILE = os.path.join(MEM_DIR, "plan.json")


def load_plan():
    try:
        with open(PLAN_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"goal": "", "persona": "", "subtasks": []}


def save_plan(plan):
    os.makedirs(MEM_DIR, exist_ok=True)
    tmp = PLAN_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(plan, f, indent=1)
    os.replace(tmp, PLAN_FILE)


CHECK_NUM_RE = re.compile(r"(level|gold|xp|hp|mana|moves)\s*(>=|<=|==|=|>|<)\s*(\d+)$")
_OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b, "<": lambda a, b: a < b,
        "=": lambda a, b: a == b, "==": lambda a, b: a == b}


def eval_check(check, tracker):
    """Verify a subtask condition against tracked game state.

    Returns (met, detail): met is True/False, or None when the state needed
    to verify is not known yet. Supported checks:
      level>=N gold>=N xp>=N hp>=N mana>=N moves>=N   (any comparator)
      item:<substring>   -- carrying it (as of the last `inventory`)
      room:<substring>   -- current room title contains it
    """
    check = check.strip()
    m = CHECK_NUM_RE.match(check)
    if m:
        key, op, want = m.group(1), m.group(2), int(m.group(3))
        cur = None
        if key in ("hp", "mana", "moves") and tracker.vitals:
            cur = tracker.vitals[("hp", "mana", "moves").index(key)]
        elif key in ("level", "gold", "xp"):
            cur = tracker.char.get(key)
        if cur is None:
            return None, "%s unknown yet (run `cmd score`)" % key
        met = _OPS[op](int(cur), want)
        return met, "%s is %s, need %s%s" % (key, cur, op, want)
    if check.startswith("item:"):
        want = check[5:].strip().lower()
        if tracker.carrying is None:
            return None, "inventory not seen yet (run `cmd inventory`)"
        met = any(want in it.lower() for it in tracker.carrying)
        return met, ("carrying '%s'" % want) if met else \
            "'%s' not in last inventory" % want
    if check.startswith("room:"):
        want = check[5:].strip().lower()
        cur = tracker.current_room or ""
        met = want in cur.lower()
        return met, "current room is %s" % (cur or "(unknown)")
    return None, "unrecognized check %r" % check


def plan_status(tracker):
    """One-line summary of the current subtask + its condition, for surfacing."""
    plan = load_plan()
    subs = plan.get("subtasks", [])
    pending = [(i, s) for i, s in enumerate(subs) if not s.get("done")]
    if not plan.get("goal") and not subs:
        return None
    if not pending:
        return "Plan '%s': ALL %d steps done" % (plan.get("goal", "?"), len(subs))
    i, s = pending[0]
    line = "Plan '%s' — step %d/%d: %s" % (
        plan.get("goal", "?"), i + 1, len(subs), s["text"])
    if s.get("check"):
        met, detail = eval_check(s["check"], tracker)
        state = {True: "MET — advance with `plan done`",
                 False: "UNMET", None: "UNVERIFIED"}[met]
        line += "\n  check [%s]: %s (%s)" % (s["check"], state, detail)
    return line

PROMPT_INLINE_RE = re.compile(r"\d+H \d+M \d+V[^\n]*?> ")
VITALS_RE = re.compile(r"(\d+)H (\d+)M (\d+)V")
EXITS_RE = re.compile(r"^\[ Exits: ([^\]]+)\]")
DIRECTIONS = {"n": "north", "s": "south", "e": "east", "w": "west",
              "u": "up", "d": "down", "ne": "northeast", "nw": "northwest",
              "se": "southeast", "sw": "southwest"}
for _d in list(DIRECTIONS.values()):
    DIRECTIONS[_d] = _d

SCORE_RANK_RE = re.compile(r"This ranks you as (.+) \(level (\d+)\)")
SCORE_XP_RE = re.compile(r"You have (\d+) exp, (\d+) gold")
SCORE_TNL_RE = re.compile(r"You need (\d+) exp to reach your next level")
SCORE_MAX_RE = re.compile(
    r"You have \d+\((\d+)\) hit, \d+\((\d+)\) mana and \d+\((\d+)\) movement")
KILL_RE = re.compile(r"^(.+) is dead!\s*R\.I\.P\.")
EXP_RE = re.compile(r"You receive (\d+) experience|You receive your share of experience")
LEVEL_RE = re.compile(r"You rise a level!")
DEATH_RE = re.compile(r"^You are dead!")
NOWAY_RE = re.compile(r"Alas, you cannot go that way")
DARK_RE = re.compile(r"It is pitch black")
INV_WORDS = {"i", "inv", "inventory"}


def read_goals():
    """The agent-owned goals block of player.md (preserved across rewrites)."""
    try:
        txt = open(PLAYER_MD).read()
        seg = txt.split(GOALS_HEADER, 1)[1].split(AUTO_MARKER, 1)[0].strip("\n")
        if seg.strip():
            return seg
    except (OSError, IndexError):
        pass
    return DEFAULT_GOALS


class MemoryTracker:
    """Parses the cleaned game stream into player.md + world.md."""

    def __init__(self):
        os.makedirs(MEM_DIR, exist_ok=True)
        self.rooms = {}           # key -> {"exits", "links", "here", "shop",
        self.char = {}            #         "signs", "hazards"}
        self.events = []
        self.current_room = None
        self.vitals = None        # (hp, mana, moves) from the latest prompt
        self.carrying = None      # list, as of the last `inventory`
        self.trail = []           # recent moves: "south: A -> B"
        self.kills_xp = []        # xp numbers of recent kills
        self.deaths = 0
        self.gold_hist = []       # gold values seen in `score`, in order
        self.moves_hist = []      # V values from recent prompts
        self._gold_session_base = None
        self._linebuf = ""
        self._recent = []         # recent lines, for room-title walk-back
        self._pending_move = None
        self._collect_room = None
        self._capture = None      # {"kind","arg","lines"} for list/read/inventory
        self._prompt_pending = False
        self._dirty = False
        try:                      # reload memory from previous sessions
            with open(MEM_STATE) as f:
                st = json.load(f)
            self.rooms = st.get("rooms", {})
            self.char = st.get("char", {})
            self.events = st.get("events", [])
            self.current_room = st.get("current_room")
            self.carrying = st.get("carrying")
            self.trail = st.get("trail", [])
            self.kills_xp = st.get("kills_xp", [])
            self.deaths = st.get("deaths", 0)
            self.gold_hist = st.get("gold_hist", [])
        except (OSError, ValueError):
            pass

    # -- hooks called by the Mud object -------------------------------------
    def sent(self, line):
        try:
            self._end_capture()
            parts = line.strip().lower().split()
            word = parts[0] if parts else ""
            arg = " ".join(parts[1:])
            self._pending_move = DIRECTIONS.get(word)
            self._collect_room = None
            self._recent.append("\x00SENT")
            # some responses are worth capturing verbatim into memory
            if word in INV_WORDS:
                self._capture = {"kind": "inventory", "arg": "", "lines": []}
            elif word == "list":
                self._capture = {"kind": "shop", "arg": arg, "lines": []}
            elif word in ("read", "examine") and arg:
                self._capture = {"kind": "sign", "arg": arg, "lines": []}
            elif word == "look" and arg and arg not in DIRECTIONS \
                    and any(w in arg for w in ("sign", "board", "note",
                                               "plaque", "inscription")):
                self._capture = {"kind": "sign", "arg": arg, "lines": []}
        except Exception:
            pass

    def feed(self, chunk):
        try:
            self._feed(chunk)
        except Exception:
            pass                  # memory must never take down the session

    def _feed(self, chunk):
        self._linebuf += chunk

        def _prompt(m):           # prompts carry vitals and act as line breaks
            v = VITALS_RE.search(m.group(0))
            self.vitals = (v.group(1), v.group(2), v.group(3))
            self.moves_hist.append(int(v.group(3)))
            del self.moves_hist[:-30]
            self._prompt_pending = True
            self._dirty = True
            return "\n"

        self._linebuf = PROMPT_INLINE_RE.sub(_prompt, self._linebuf)
        while "\n" in self._linebuf:
            line, self._linebuf = self._linebuf.split("\n", 1)
            self._line(line.rstrip())
        if self._prompt_pending:  # the response is complete: close any capture
            self._prompt_pending = False
            self._end_capture()
        self.flush()

    # -- per-line parsing -----------------------------------------------------
    def _line(self, line):
        self._recent.append(line)
        del self._recent[:-40]

        if self._capture is not None and line.strip():
            if len(self._capture["lines"]) < 25:
                self._capture["lines"].append(line.strip())

        if self._collect_room is not None:      # room contents after the exits line
            if not line.strip():
                self._collect_room = None
            elif (len(self.rooms[self._collect_room]["here"]) < 8
                  and not line.startswith("You")):
                self.rooms[self._collect_room]["here"].append(line.strip())
                self._dirty = True
            return

        m = EXITS_RE.match(line.strip())
        if m:
            self._room(m.group(1).strip())
            return
        if NOWAY_RE.search(line):
            self._pending_move = None
            return
        if DARK_RE.search(line):                # moved into an unlit room
            if self._pending_move and self.current_room in self.rooms:
                self._hazard(self.current_room,
                             "darkness through %s (bring a light source)"
                             % self._pending_move)
                self.trail.append("%s: %s → (darkness)"
                                  % (self._pending_move, self.current_room))
                del self.trail[:-15]
            self.current_room = None            # position unknown until lit room
            self._pending_move = None
            self._dirty = True
            return
        m = KILL_RE.match(line.strip())
        if m and not line.startswith("You are"):
            self._event("Killed %s" % m.group(1).strip())
            return
        m = EXP_RE.search(line)
        if m:
            xp = m.group(1) or "shared"
            if m.group(1):
                self.kills_xp.append(int(m.group(1)))
                del self.kills_xp[:-10]
            if self.events and self.events[-1].startswith("Killed") \
                    and "xp)" not in self.events[-1]:
                self.events[-1] += " (+%s xp)" % xp
            else:
                self._event("Gained %s xp" % xp)
            return
        if LEVEL_RE.search(line):
            if "level" in self.char:
                self.char["level"] = str(int(self.char["level"]) + 1)
            self._event("LEVEL UP! Now level %s" % self.char.get("level", "?"))
            return
        if DEATH_RE.match(line.strip()):
            self.deaths += 1
            if self.current_room in self.rooms:
                self._hazard(self.current_room, "a death occurred here")
            self._event("DIED near %s — respawned at the temple; corpse (with "
                        "gear) left behind" % (self.current_room or "?"))
            return
        for rx, keys in ((SCORE_RANK_RE, ("rank", "level")),
                         (SCORE_XP_RE, ("xp", "gold")),
                         (SCORE_TNL_RE, ("xp_to_next",)),
                         (SCORE_MAX_RE, ("max_hp", "max_mana", "max_moves"))):
            m = rx.search(line)
            if m:
                self.char.update(zip(keys, m.groups()))
                if rx is SCORE_XP_RE:
                    gold = int(m.group(2))
                    if self._gold_session_base is None:
                        self._gold_session_base = gold
                    if not self.gold_hist or self.gold_hist[-1] != gold:
                        self.gold_hist.append(gold)
                        del self.gold_hist[:-10]
                self._dirty = True

    def _hazard(self, room_key, text):
        hz = self.rooms[room_key].setdefault("hazards", [])
        if text not in hz:
            hz.append(text)
            self._dirty = True

    def _end_capture(self):
        cap, self._capture = self._capture, None
        if not cap or not cap["lines"]:
            return
        if cap["kind"] == "inventory":
            lines = [l for l in cap["lines"]
                     if l not in ("You are carrying:", "Nothing.")]
            self.carrying = [re.sub(r"^\(\s*\d+\)\s*", "", l) for l in lines]
        elif cap["kind"] == "shop" and self.current_room in self.rooms:
            # only keep it if it looks like a price table, not an error message
            if any(re.search(r"\d", l) for l in cap["lines"]):
                self.rooms[self.current_room]["shop"] = cap["lines"]
        elif cap["kind"] == "sign" and self.current_room in self.rooms:
            text = " ".join(cap["lines"])[:300]
            if "You do not see that" in text or "does not seem to" in text:
                return
            signs = self.rooms[self.current_room].setdefault("signs", [])
            signs[:] = [s for s in signs if not s.startswith(cap["arg"] + ":")]
            signs.append("%s: %s" % (cap["arg"], text))
            del signs[:-5]
        self._dirty = True

    @staticmethod
    def _base(key):
        """Room key without a ' (2)' disambiguation suffix."""
        return re.sub(r" \(\d+\)$", "", key)

    def _room_key(self, title, exits):
        """Map a seen title to a room key, keeping same-titled rooms apart.

        Identity heuristics, in order of trust: the map link we just followed;
        staying in the current room (a re-look, possibly with a door now open);
        an existing same-title room with identical exits; otherwise it's a new
        room and gets a numbered variant key.
        """
        if self._pending_move and self.current_room in self.rooms:
            dest = self.rooms[self.current_room]["links"].get(self._pending_move)
            if dest and dest in self.rooms and self._base(dest) == title:
                return dest
        if not self._pending_move and self.current_room \
                and self._base(self.current_room) == title:
            return self.current_room
        variants = [k for k in self.rooms if self._base(k) == title]
        for k in variants:
            if self.rooms[k]["exits"] == exits:
                return k
        if not variants:
            return title
        return "%s (%d)" % (title, len(variants) + 1)

    def _room(self, exits):
        # title = first non-blank line after the last blank/[SENT] boundary
        idx = len(self._recent) - 2
        boundary = -1
        for i in range(idx, -1, -1):
            if not self._recent[i].strip() or self._recent[i] == "\x00SENT":
                boundary = i
                break
        title = None
        for i in range(boundary + 1, idx + 1):
            if self._recent[i].strip():
                title = self._recent[i].strip()
                break
        # real room titles are short and never end in sentence punctuation --
        # this keeps event lines ("The dog leaves west.") out of the map
        if (not title or len(title) > 60 or title[-1] in ".!?,;:'\""
                or title.startswith("You ")):
            self._pending_move = None
            return
        key = self._room_key(title, exits)
        room = self.rooms.setdefault(key, {"exits": exits, "links": {}, "here": []})
        room["exits"] = exits
        room["here"] = []
        self._collect_room = key
        if (self._pending_move and self.current_room
                and self.current_room != key and self.current_room in self.rooms):
            self.rooms[self.current_room]["links"][self._pending_move] = key
            self.trail.append("%s: %s → %s"
                              % (self._pending_move, self.current_room, key))
            del self.trail[:-15]
        self.current_room = key
        self._pending_move = None
        self._dirty = True

    def _event(self, text):
        self.events.append(text)
        del self.events[:-30]
        self._dirty = True

    # -- rendering ------------------------------------------------------------
    def flush(self):
        if not self._dirty:
            return
        self._dirty = False
        try:
            self._write_state()
            self._write_player()
            self._write_world()
        except OSError:
            pass

    def _write_state(self):
        tmp = MEM_STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"rooms": self.rooms, "char": self.char,
                       "events": self.events,
                       "current_room": self.current_room,
                       "carrying": self.carrying, "trail": self.trail,
                       "kills_xp": self.kills_xp, "deaths": self.deaths,
                       "gold_hist": self.gold_hist}, f, indent=1)
        os.replace(tmp, MEM_STATE)

    def _signals(self):
        """Small computed block: trends the agent should reason from."""
        out = []
        if self.kills_xp:
            n = self.kills_xp[-5:]
            avg = sum(n) / len(n)
            out.append("Avg XP/kill (last %d): %.0f" % (len(n), avg))
            tnl = self.char.get("xp_to_next")
            if tnl and avg > 0:
                out.append("XP to next level: %s → ~%d more kills at this rate"
                           % (tnl, -(-int(tnl) // int(avg))))
        elif self.char.get("xp_to_next"):
            out.append("XP to next level: %s (no measured kills yet)"
                       % self.char["xp_to_next"])
        if len(self.moves_hist) >= 2:
            delta = self.moves_hist[-1] - self.moves_hist[0]
            out.append("Moves: %d now, %+d over the last %d prompts"
                       % (self.moves_hist[-1], delta, len(self.moves_hist)))
        if self.gold_hist:
            base = self._gold_session_base
            cur = self.gold_hist[-1]
            trend = " (%+d this session)" % (cur - base) if base is not None else ""
            out.append("Gold: %d%s" % (cur, trend))
        out.append("Deaths recorded: %d" % self.deaths)
        untried = sum(len(self._untried(k)) for k in self.rooms)
        out.append("Frontier: %d untried exits across %d mapped rooms"
                   % (untried, len(self.rooms)))
        return "\n".join("- " + s for s in out)

    def _untried(self, key):
        """Exit directions of a room not yet followed to a known destination."""
        r = self.rooms[key]
        exits = [DIRECTIONS.get(e.strip("()").lower())
                 for e in r["exits"].split()]
        return [e for e in exits if e and e not in r.get("links", {})]

    def _write_player(self):
        c = self.char
        vit = ("HP %s · Mana %s · Moves %s" % self.vitals
               if self.vitals else "(unknown — no prompt seen yet)")
        if c.get("max_hp"):
            vit += "  (max %s/%s/%s)" % (c["max_hp"], c["max_mana"], c["max_moves"])
        bits = []
        if c.get("rank"):
            bits.append("%s — level %s" % (c["rank"], c["level"]))
        if c.get("xp"):
            bits.append("XP %s (%s to next level) · %s gold"
                        % (c["xp"], c.get("xp_to_next", "?"), c.get("gold", "?")))
        charline = "\n".join(bits) or "(unknown — run `cmd score` once)"
        events = "\n".join("- " + e for e in self.events) or "- (nothing yet)"
        plan = load_plan()
        persona = plan.get("persona") or \
            '(none set — set one with: mud_session.py persona "...")'
        plan_lines = []
        if plan.get("goal") or plan.get("subtasks"):
            plan_lines.append("Goal: %s" % (plan.get("goal") or "(unset)"))
            cur_found = False
            for i, s in enumerate(plan.get("subtasks", [])):
                mark = "x" if s.get("done") else " "
                line = "%d. [%s] %s" % (i + 1, mark, s["text"])
                if not s.get("done") and not cur_found:
                    cur_found = True
                    line += "   ← CURRENT"
                    if s.get("check"):
                        met, detail = eval_check(s["check"], self)
                        state = {True: "MET", False: "UNMET",
                                 None: "UNVERIFIED"}[met]
                        line += "\n   check [%s]: %s — %s" \
                                % (s["check"], state, detail)
                elif s.get("check"):
                    line += "  (check: %s)" % s["check"]
                plan_lines.append(line)
        plan_block = "\n".join(plan_lines) or \
            '(no plan — create one with: mud_session.py plan set "..." ' \
            'then plan add "..." --check "level>=N")'
        if self.carrying is None:
            carrying = "(not seen yet — run `cmd inventory`)"
        elif not self.carrying:
            carrying = "(nothing)"
        else:
            carrying = "\n".join("- " + c for c in self.carrying)
        body = (
            "# Player memory — %s@%s:%d\n\n%s\n%s\n\n%s\n\n"
            "## Persona (apply this style to every decision)\n%s\n\n"
            "## Plan (managed via `plan` subcommands)\n%s\n\n"
            "## Vitals (live, from the game prompt)\n%s\n\n"
            "## Character (from the last `score`)\n%s\n\n"
            "## Signals (computed — watch these, adapt strategy)\n%s\n\n"
            "## Carrying (as of the last `inventory`)\n%s\n\n"
            "## Current location\n%s — map, frontier and hazards in world.md\n\n"
            "## Recent events (oldest first)\n%s\n"
            % (USER, HOST, PORT, GOALS_HEADER, read_goals(), AUTO_MARKER,
               persona, plan_block, vit, charline, self._signals(), carrying,
               self.current_room or "(unknown)", events))
        tmp = PLAYER_MD + ".tmp"
        with open(tmp, "w") as f:
            f.write(body)
        os.replace(tmp, PLAYER_MD)

    def _write_world(self):
        lines = ["# World map — auto-updated in real time by mud_session.py",
                 "_Don't edit by hand (notes belong in player.md). "
                 "`links` are observed one-way passages._",
                 "",
                 "Current room: **%s**" % (self.current_room or "(unknown)"), ""]
        for title, r in self.rooms.items():
            lines.append("## %s" % title)
            lines.append("- Exits: %s" % r["exits"])
            for d, dest in r["links"].items():
                lines.append("- %s → %s" % (d, dest))
            for hz in r.get("hazards", []):
                lines.append("- ⚠ %s" % hz)
            if r.get("shop"):
                lines.append("- Shop stock (from `list`): "
                             + " | ".join(r["shop"]))
            for sg in r.get("signs", []):
                lines.append('- Sign — %s' % sg)
            if r["here"]:
                lines.append("- Last seen here: " + " | ".join(r["here"]))
            lines.append("")
        frontier = [(k, self._untried(k)) for k in self.rooms]
        frontier = [(k, u) for k, u in frontier if u]
        lines.append("## Frontier — untried exits (explore these)")
        if frontier:
            for k, u in frontier:
                lines.append("- %s: %s" % (k, ", ".join(u)))
        else:
            lines.append("- (none — every known exit has been followed)")
        lines.append("")
        lines.append("## Trail — recent moves (oldest first)")
        lines += ["- " + t for t in self.trail] or ["- (no moves yet)"]
        lines.append("")
        tmp = WORLD_MD + ".tmp"
        with open(tmp, "w") as f:
            f.write("\n".join(lines))
        os.replace(tmp, WORLD_MD)


class Mud:
    """One live telnet connection + cleaned-text buffer."""

    def __init__(self):
        self.sock = socket.create_connection((HOST, PORT), timeout=15)
        self.sock.setblocking(False)
        self._telnet_pending = b""
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.text = ""            # cleaned, not-yet-consumed output
        self._pager_pos = 0       # how far pager auto-continue has scanned
        self.last_prompt = ""
        self.started_at = time.time()
        self.alive = True
        self._transcript = open(TRANSCRIPT, "a")
        self.tracker = MemoryTracker()

    # -- low level ---------------------------------------------------------
    def _strip_telnet(self, data):
        """Remove telnet IAC sequences, politely refusing all options."""
        data = self._telnet_pending + data
        self._telnet_pending = b""
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b != IAC:
                out.append(b)
                i += 1
                continue
            if i + 1 >= len(data):          # incomplete sequence: keep for later
                self._telnet_pending = data[i:]
                break
            cmd = data[i + 1]
            if cmd == IAC:                   # escaped 0xff data byte
                out.append(IAC)
                i += 2
            elif cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= len(data):
                    self._telnet_pending = data[i:]
                    break
                opt = data[i + 2]
                try:
                    if cmd == DO:
                        self.sock.sendall(bytes([IAC, WONT, opt]))
                    elif cmd == WILL:
                        self.sock.sendall(bytes([IAC, DONT, opt]))
                except OSError:
                    pass
                i += 3
            elif cmd == SB:                  # subnegotiation: skip to IAC SE
                end = data.find(bytes([IAC, SE]), i + 2)
                if end == -1:
                    self._telnet_pending = data[i:]
                    break
                i = end + 2
            else:
                i += 2
        return bytes(out)

    def _clean(self, data):
        text = self._decoder.decode(self._strip_telnet(data))
        return ANSI_RE.sub("", text).replace("\r", "")

    def pump(self, wait=0.0):
        """Read whatever the MUD has sent (within `wait`s); buffer it cleaned."""
        r, _, _ = select.select([self.sock], [], [], wait)
        if not r:
            return False
        try:
            data = self.sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return False
        except OSError:
            self.alive = False
            return False
        if not data:
            self.alive = False
            return False
        cleaned = self._clean(data)
        if cleaned:
            self.text += cleaned
            self._transcript.write(cleaned)
            self._transcript.flush()
            self.tracker.feed(cleaned)          # memory updates in real time
        return True

    def send_line(self, line):
        self.sock.sendall(line.encode() + b"\n")
        self._transcript.write("\n[SENT] %s\n" % line)
        self._transcript.flush()
        self.tracker.sent(line)

    def consume(self):
        out, self.text = self.text, ""
        self._pager_pos = 0
        m = re.search(r"(\d+H \d+M \d+V[^\n]*>)\s?$", out)
        if m:
            self.last_prompt = m.group(1)
        return out

    # -- prompt-driven reading ---------------------------------------------
    def _auto_page(self):
        """If the pager is asking 'Press return', press it (once per prompt)."""
        m = PAGER_RE.search(self.text, self._pager_pos)
        if m:
            self._pager_pos = len(self.text)
            self.sock.sendall(b"\n")     # continue, without a [SENT] entry
            return True
        return False

    def wait_prompt(self, timeout=8.0):
        """Read until the in-game prompt is at the end of the buffer."""
        end = time.time() + timeout
        while time.time() < end:
            if GAME_PROMPT_RE.search(self.text) or self.text.endswith("> "):
                return True
            if not self.alive:
                return False
            self._auto_page()
            self.pump(0.1)
        return False

    def expect(self, pattern, timeout=15.0, label=""):
        """Read until `pattern` appears anywhere in the buffer."""
        rx = re.compile(pattern)
        end = time.time() + timeout
        while time.time() < end:
            m = rx.search(self.text)
            if m:
                return m
            if not self.alive:
                raise SessionError(
                    "Server closed the connection while waiting for %s.\n"
                    "Last output:\n%s" % (label or pattern, self.text[-500:]))
            self.pump(0.1)
        raise SessionError(
            "Timed out waiting for %s.\nLast output:\n%s"
            % (label or pattern, self.text[-500:]))

    # -- login --------------------------------------------------------------
    def login(self):
        """Drive the tbaMUD login sequence end to end; return the game intro."""
        self.expect(r"By what name", label="the name prompt")
        self.send_line(USER)
        m = self.expect(r"Password:|Did I get that right|Wrong password",
                        label="the password prompt")
        if "Did I get that right" in m.group(0):
            self.send_line("N")   # don't create a new character by accident
            raise SessionError(
                "Character %r does not exist on this server "
                "(it offered to create it; refused)." % USER)
        self.send_line(PASSWORD)
        m = self.expect(
            r"\*\*\* PRESS RETURN:|Make your choice:|Wrong password",
            label="the post-password screen")
        if "Wrong password" in m.group(0):
            raise SessionError("Wrong password for %r." % USER)
        if "PRESS RETURN" in m.group(0):
            self.send_line("")
            self.expect(r"Make your choice:", label="the main menu")
        self.send_line("1")       # menu option 1: enter the game
        if not self.wait_prompt(15):
            raise SessionError(
                "Logged in but never saw the game prompt.\nLast output:\n%s"
                % self.text[-500:])
        return self.consume()

    def close(self):
        self.alive = False
        self.tracker.flush()
        try:
            self.sock.close()
        except OSError:
            pass
        self._transcript.write("\n[SESSION CLOSED]\n")
        self._transcript.close()


# --- daemon side ------------------------------------------------------------

def serve(mud):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(SOCK_PATH)
    listener.listen(4)
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    try:
        while mud.alive:
            r, _, _ = select.select([listener, mud.sock], [], [], 1.0)
            if mud.sock in r:
                mud.pump(0)          # buffer async output (combat, chat, ...)
                mud._auto_page()
            if listener in r:
                conn, _ = listener.accept()
                try:
                    if handle(conn, mud):   # True => stop requested
                        break
                except Exception as e:      # keep the session alive on bad requests
                    try:
                        conn.sendall((json.dumps(
                            {"ok": False, "error": str(e)}) + "\n").encode())
                    except OSError:
                        pass
                finally:
                    conn.close()
    finally:
        mud.close()
        for p in (SOCK_PATH, PIDFILE):
            try:
                os.unlink(p)
            except OSError:
                pass


def handle(conn, mud):
    conn.settimeout(30)
    buf = b""
    while not buf.endswith(b"\n"):
        d = conn.recv(65536)
        if not d:
            return False
        buf += d
    req = json.loads(buf)
    op = req.get("op")

    if op == "send":
        pre = mud.consume()                       # async output queued earlier
        mud.send_line(req["line"])
        got_prompt = mud.wait_prompt(float(req.get("timeout", 8)))
        body = mud.consume()
        reply = {"ok": True, "text": pre + body, "prompt": mud.last_prompt,
                 "saw_prompt": got_prompt, "alive": mud.alive}
    elif op == "recv":
        deadline = time.time() + float(req.get("wait", 1.0))
        while time.time() < deadline and mud.alive:
            mud.pump(0.1)
            mud._auto_page()
        reply = {"ok": True, "text": mud.consume(), "prompt": mud.last_prompt,
                 "alive": mud.alive}
    elif op == "status":
        reply = {"ok": True, "alive": mud.alive, "host": HOST, "port": PORT,
                 "user": USER, "prompt": mud.last_prompt,
                 "uptime_s": round(time.time() - mud.started_at, 1),
                 "transcript": TRANSCRIPT, "memory": MEM_DIR,
                 "room": mud.tracker.current_room,
                 "rooms_mapped": len(mud.tracker.rooms),
                 "plan": plan_status(mud.tracker),
                 "persona": load_plan().get("persona", "")}
    elif op == "stop":
        mud.send_line("quit")               # in-game quit drops to the menu...
        deadline = time.time() + 3
        while time.time() < deadline and mud.alive:
            mud.pump(0.1)
            if "Make your choice:" in mud.text:
                mud.send_line("0")          # ...menu option 0 disconnects cleanly
                deadline = time.time() + 2
                mud.text = mud.text.replace("Make your choice:", "", 1)
        reply = {"ok": True, "text": mud.consume()}
        conn.sendall((json.dumps(reply) + "\n").encode())
        return True
    else:
        reply = {"ok": False, "error": "unknown op %r" % op}

    conn.sendall((json.dumps(reply) + "\n").encode())
    return False


def daemonize():
    """Detach into the background; stdio goes to daemon.log."""
    if os.fork() > 0:
        return False                              # parent: keep running CLI
    os.setsid()
    devnull = os.open(os.devnull, os.O_RDONLY)
    logfd = os.open(DAEMON_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    os.dup2(devnull, 0)
    os.dup2(logfd, 1)
    os.dup2(logfd, 2)
    return True                                   # child: become the daemon


# --- client side --------------------------------------------------------------

def rpc(payload):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        c.connect(SOCK_PATH)
    except (FileNotFoundError, ConnectionRefusedError):
        sys.exit("No active MUD session. Start one with:\n"
                 "  %s start" % sys.argv[0])
    c.settimeout(float(payload.get("timeout", 8)) + 25)
    c.sendall((json.dumps(payload) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        d = c.recv(65536)
        if not d:
            break
        buf += d
    c.close()
    if not buf:
        sys.exit("Session daemon did not answer (it may have just shut down).")
    return json.loads(buf)


def session_running():
    if not os.path.exists(SOCK_PATH):
        return False
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        c.connect(SOCK_PATH)
        c.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        os.unlink(SOCK_PATH)                      # stale socket from a dead daemon
        return False


# --- CLI ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="op", required=True)
    sub.add_parser("start", help="connect, log in, run session in background")
    p = sub.add_parser("cmd", help="send one game command, print the response")
    p.add_argument("words", nargs="+", help="the command, e.g.: look")
    p.add_argument("--timeout", type=float, default=8)
    p = sub.add_parser("recv", help="collect async output without sending anything")
    p.add_argument("--wait", type=float, default=1.5)
    sub.add_parser("status", help="show session state")
    p = sub.add_parser("log", help="tail the session transcript")
    p.add_argument("-n", type=int, default=40)
    sub.add_parser("stop", help="quit the game and stop the session")
    p = sub.add_parser("goal", help="add a free-form note/goal to data/player.md")
    p.add_argument("words", nargs="+", help='e.g.: goal "guard too strong at lvl 3"')
    sub.add_parser("memory", help="print data/player.md and data/world.md")
    p = sub.add_parser("plan", help="manage the long-term plan (set/add/done/show)")
    p.add_argument("action", nargs="?", default="show",
                   choices=["set", "add", "done", "show"])
    p.add_argument("words", nargs="*")
    p.add_argument("--check", help='verifiable condition, e.g. "level>=7", '
                                   '"item:lamp", "gold>=120", "room:temple"')
    p = sub.add_parser("persona", help="set or show the play style to apply")
    p.add_argument("words", nargs="*")
    p = sub.add_parser("find", help="search rooms, shops, signs, events, plan")
    p.add_argument("words", nargs="+")
    args = ap.parse_args()

    if args.op == "start":
        os.makedirs(SESSION_DIR, exist_ok=True)
        if session_running():
            sys.exit("A session is already running (use `status`, or `stop` first).")
        try:
            mud = Mud()
        except OSError as e:
            sys.exit("Cannot reach the MUD at %s:%d — is the server up? (%s)"
                     % (HOST, PORT, e))
        try:
            intro = mud.login()
        except SessionError as e:
            mud.close()
            sys.exit("Login failed: %s" % e)
        if daemonize():
            serve(mud)                            # child never returns here
            sys.exit(0)
        print(intro.rstrip())
        print("\n[session started: %s@%s:%d — transcript: %s]"
              % (USER, HOST, PORT, TRANSCRIPT))
        print("[memory: %s — %d rooms mapped so far; consult player.md & "
              "world.md before deciding what to do]"
              % (MEM_DIR, len(mud.tracker.rooms)))
        persona = load_plan().get("persona")
        if persona:
            print("[persona] %s" % persona)
        ps = plan_status(mud.tracker)
        if ps:
            print("[plan] %s" % ps)
        print("[notes]\n%s" % read_goals())

    elif args.op == "cmd":
        r = rpc({"op": "send", "line": " ".join(args.words),
                 "timeout": args.timeout})
        print(r["text"].rstrip())
        if not r.get("saw_prompt"):
            print("[warning: no prompt within %.0fs — output may be partial; "
                  "use `recv` to collect the rest]" % args.timeout,
                  file=sys.stderr)
        if not r.get("alive"):
            print("[session ended — the server closed the connection]",
                  file=sys.stderr)

    elif args.op == "recv":
        r = rpc({"op": "recv", "wait": args.wait})
        out = r["text"].rstrip()
        print(out if out else "[no new output]")

    elif args.op == "status":
        if not session_running():
            print("No active session.")
            return
        r = rpc({"op": "status"})
        print("Session: %s@%s:%d  alive=%s  uptime=%.0fs"
              % (r["user"], r["host"], r["port"], r["alive"], r["uptime_s"]))
        print("Last prompt: %s" % (r["prompt"] or "(none yet)"))
        print("Room:        %s  (%d rooms mapped)"
              % (r.get("room") or "(unknown)", r.get("rooms_mapped", 0)))
        print("Transcript:  %s" % r["transcript"])
        print("Memory:      %s" % r.get("memory", MEM_DIR))
        if r.get("persona"):
            print("Persona:     %s" % r["persona"])
        if r.get("plan"):
            print(r["plan"])
        print("Notes:\n%s" % read_goals())

    elif args.op == "log":
        if not os.path.exists(TRANSCRIPT):
            sys.exit("No transcript at %s" % TRANSCRIPT)
        with open(TRANSCRIPT) as f:
            lines = f.readlines()
        sys.stdout.write("".join(lines[-args.n:]))

    elif args.op == "stop":
        r = rpc({"op": "stop", "timeout": 5})
        out = r.get("text", "").rstrip()
        if out:
            print(out)
        print("[session stopped]")

    elif args.op == "goal":
        os.makedirs(MEM_DIR, exist_ok=True)
        goals = read_goals()
        if goals == DEFAULT_GOALS:
            goals = ""
        goals = (goals + "\n" if goals else "") + "- " + " ".join(args.words)
        try:                       # keep whatever auto content already exists
            auto = AUTO_MARKER + open(PLAYER_MD).read().split(AUTO_MARKER, 1)[1]
        except (OSError, IndexError):
            auto = AUTO_MARKER + "\n\n(auto sections appear once a session runs)\n"
        tmp = PLAYER_MD + ".tmp"
        with open(tmp, "w") as f:
            f.write("# Player memory — %s@%s:%d\n\n%s\n%s\n\n%s"
                    % (USER, HOST, PORT, GOALS_HEADER, goals, auto))
        os.replace(tmp, PLAYER_MD)
        print("Goal recorded in %s:\n%s" % (PLAYER_MD, goals))

    elif args.op == "memory":
        for path in (PLAYER_MD, WORLD_MD):
            print("=" * 8, path, "=" * 8)
            try:
                print(open(path).read().rstrip())
            except OSError:
                print("(not created yet — start a session first)")

    elif args.op == "plan":
        plan = load_plan()
        text = " ".join(args.words)
        if args.action == "set":
            if not text:
                sys.exit('Usage: plan set "the long-term goal"')
            plan["goal"] = text
            plan["subtasks"] = []
            save_plan(plan)
            print("Plan goal set: %s\nNow add ordered steps with: "
                  'plan add "..." [--check "level>=N"]' % text)
        elif args.action == "add":
            if not text:
                sys.exit('Usage: plan add "subtask" [--check "item:lamp"]')
            plan.setdefault("subtasks", []).append(
                {"text": text, "check": args.check, "done": False})
            save_plan(plan)
            print("Added step %d: %s%s"
                  % (len(plan["subtasks"]), text,
                     " (check: %s)" % args.check if args.check else ""))
        elif args.action == "done":
            pending = [s for s in plan.get("subtasks", []) if not s.get("done")]
            if not pending:
                sys.exit("Nothing to mark done.")
            pending[0]["done"] = True
            save_plan(plan)
            print("Done: %s" % pending[0]["text"])
            print("Reflect: record what you learned with `goal \"...\"`, "
                  "then check the next step.")
        # always show the plan with a live evaluation afterwards
        print(plan_status(MemoryTracker()) or "(no plan yet)")

    elif args.op == "persona":
        plan = load_plan()
        if args.words:
            plan["persona"] = " ".join(args.words)
            save_plan(plan)
            print("Persona set: %s" % plan["persona"])
        else:
            print(plan.get("persona") or "(no persona set)")

    elif args.op == "find":
        term = " ".join(args.words).lower()
        t = MemoryTracker()
        hits = []
        for key, r in t.rooms.items():
            fields = ([("room", key), ("exits", r["exits"])]
                      + [("links", "%s → %s" % (d, dst))
                         for d, dst in r.get("links", {}).items()]
                      + [("hazard", h) for h in r.get("hazards", [])]
                      + [("shop", s) for s in r.get("shop", [])]
                      + [("sign", s) for s in r.get("signs", [])]
                      + [("seen", s) for s in r.get("here", [])])
            for kind, val in fields:
                if term in val.lower() or term in key.lower():
                    hits.append("%s @ %s: %s" % (kind, key, val))
        for e in t.events:
            if term in e.lower():
                hits.append("event: %s" % e)
        for c in (t.carrying or []):
            if term in c.lower():
                hits.append("carrying: %s" % c)
        plan = load_plan()
        for s in plan.get("subtasks", []):
            if term in s["text"].lower():
                hits.append("plan step: %s" % s["text"])
        for note in read_goals().splitlines():
            if term in note.lower():
                hits.append("note: %s" % note.strip("- "))
        seen = set()
        hits = [h for h in hits if not (h in seen or seen.add(h))]
        print("\n".join(hits[:40]) or "(no matches in memory)")
        try:                       # the transcript remembers what memory doesn't
            tlines = [l.rstrip() for l in open(TRANSCRIPT)
                      if term in l.lower()]
            if tlines:
                print("--- transcript (last %d of %d matching lines) ---"
                      % (min(5, len(tlines)), len(tlines)))
                print("\n".join(tlines[-5:]))
        except OSError:
            pass


if __name__ == "__main__":
    main()
