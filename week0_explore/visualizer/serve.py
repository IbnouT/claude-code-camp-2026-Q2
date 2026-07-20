#!/usr/bin/env python3
"""MUD Observatory server.

Serves the built UI (dist/) and GET /state — the play-mud store adapted into
the visualizer's contract. Stdlib only; Node is never needed at runtime.

    python3 serve.py [--data <dir>] [--port 8790]
    python3 serve.py --selftest

The adapter reads (all optional, absence degrades gracefully):
    <data>/.mud_memory.json   rooms/links/position/events/char/trail/deaths
    <data>/player.md          the one live-vitals line (HP · Mana · Moves)
    <data>/plan.json          goal / persona / subtasks

Contract returned by /state:
    rooms{key: {title, exits[], flags[], hazards[]}}, links[{from,dir,to}],
    trail[{from,dir,to}], position, vitals{}, deaths, events[], plan{}, thought,
    hash. With ?hash=<h> returns {"unchanged": true} when nothing moved.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
DEFAULT_DATA = os.path.normpath(os.path.join(
    HERE, "..", "explore_architecture", "02_agent_skills", "data"))
# the world files the local server actually runs (docker mounts this lib/)
DEFAULT_WORLD = os.path.normpath(os.path.join(
    HERE, "..", "infrastructure", "lib", "world", "wld"))

DIRECTIONS = {"n": "north", "s": "south", "e": "east", "w": "west",
              "u": "up", "d": "down", "ne": "northeast", "nw": "northwest",
              "se": "southeast", "sw": "southwest"}
VITALS_RE = re.compile(r"HP (\d+) · Mana (\d+) · Moves (\d+)")
TRAIL_RE = re.compile(r"^(\w+): (.*) → (.*)$")
DEFAULT_TRANSCRIPT = os.path.expanduser("~/.play_mud/localhost_4000/transcript.log")

SENT_RE = re.compile(r"^\[SENT\] (.*)$")
COMBAT_LINE_RE = re.compile(
    r"hits? you|you hit|you miss|misses you|You (barely |lightly )?"
    r"(tickle|slash|pierce|pound|crush|whack|smite)|parr(y|ies)|dodges?|"
    r"is dead!|death cry|You flee|flees|Your (slash|hit|pierce|crush)", re.I)
FIGHT_VERBS = {"kill", "hit", "attack", "bash", "kick", "backstab", "cast"}
REST_VERBS = {"rest", "sleep", "sit"}
SHOP_VERBS = {"list", "buy", "sell", "value"}
READ_VERBS = {"read", "examine"}


def tail_lines(path, max_bytes=20000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read().decode("utf-8", "replace")
        mtime = os.path.getmtime(path)
    except OSError:
        return [], None
    lines = [l.rstrip() for l in data.split("\n")]
    if size > max_bytes and len(lines) > 1:
        lines = lines[1:]  # first line was cut mid-way by the seek
    return lines, mtime


def derive_activity(transcript_path, position, data_dir=None):
    """What is the agent doing right now? Derived from the session transcript
    (every command sent + every game line), so no skill changes are needed."""
    import time
    lines, mtime = tail_lines(transcript_path)
    out = {"activity": None, "feed": [], "combat": None, "quiet_seconds": None}
    if not lines:
        return out
    out["feed"] = [l for l in lines if l.strip()][-40:]
    quiet = int(time.time() - mtime) if mtime else None
    # quantized so the state hash doesn't churn every second
    out["quiet_seconds"] = (quiet // 5) * 5 if quiet is not None else None

    # last command sent, and everything the game answered since
    last_sent, since = None, []
    for l in lines:
        m = SENT_RE.match(l)
        if m:
            last_sent, since = m.group(1).strip(), []
        elif l.strip():
            since.append(l)
    word = (last_sent or "").lower().split(" ")[0]
    arg = " ".join((last_sent or "").split(" ")[1:])

    recent = since[-12:]
    fighting = word in FIGHT_VERBS and not any(
        re.search(r"is dead!|You are dead!|You flee", l) for l in since)
    fighting = fighting or any(COMBAT_LINE_RE.search(l) for l in recent[-4:])
    died = any("You are dead!" in l for l in recent)

    if died:
        act = {"kind": "dead", "detail": "died — corpse run ahead"}
    elif fighting:
        foe = arg or next((l for l in recent if COMBAT_LINE_RE.search(l)), "")
        combat_lines = [l for l in since if l.strip()][-25:]
        out["combat"] = {"foe": arg or "enemy", "lines": combat_lines}
        act = {"kind": "fighting", "detail": "fighting %s" % (arg or "an enemy")}
    elif word in REST_VERBS:
        d = "resting — recovering vitals"
        if quiet is not None and quiet > 10:
            d = "resting %ds — vitals regenerate over time" % quiet
        act = {"kind": "resting", "detail": d}
    elif word in SHOP_VERBS:
        act = {"kind": "shopping", "detail": "trading (%s)" % last_sent}
    elif word in READ_VERBS or (word == "look" and arg):
        act = {"kind": "reading", "detail": "studying %s" % (arg or "the room")}
    elif word in DIRECTIONS or word in DIRECTIONS.values() or word == "look":
        act = {"kind": "exploring", "detail": "exploring"}
    elif last_sent:
        act = {"kind": "busy", "detail": last_sent}
    else:
        act = {"kind": "idle", "detail": "no commands yet"}

    # game-quiet doesn't mean idle: the agent may be working on its memory.
    # Resting is deliberately quiet, so it never becomes "thinking".
    if quiet is not None and quiet > 15 and act["kind"] not in ("dead", "resting"):
        act = {"kind": "thinking",
               "detail": "quiet for %ds — deciding the next move" % quiet}
        if data_dir:
            freshest, fname = None, None
            for f, label in (("plan.json", "updating its plan"),
                             ("player.md", "writing notes/goals")):
                try:
                    m = os.path.getmtime(os.path.join(data_dir, f))
                except OSError:
                    continue
                if freshest is None or m > freshest:
                    freshest, fname = m, label
            if freshest is not None and time.time() - freshest < 20:
                act = {"kind": "reading",
                       "detail": "off-game: %s" % fname}
    out["activity"] = act
    return out


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def world_map():
    """Rooms/links/position from the true-world localizer (exact vnums).

    The visualizer is an observer, not the player: it may know the real world.
    Shown = rooms the agent actually visited, plus a one-ring halo of true
    neighbors as ghosts. The playing agent's memory stays discovery-based.
    """
    wt = Handler.world
    wt.update()
    loc = wt.graph, wt.loc
    graph, l = loc
    rooms, links = {}, []
    for v in sorted(l.visited):
        hz = l.hazards.get(v, [])
        flags = []
        if any("death" in h for h in hz):
            flags.append("death")
        if hz:
            flags.append("hazard")
        rooms[str(v)] = {"title": graph[v]["title"], "exits":
                         list(graph[v]["exits"]), "flags": flags, "hazards": hz}
    for (a, d), b in l.edges.items():
        links.append({"from": str(a), "dir": d, "to": str(b)})
    for v in sorted(l.visited):                    # true-neighbor ghost halo
        for d, to in graph[v]["exits"].items():
            if to in l.visited or (v, d) in l.edges:
                continue
            if str(to) not in rooms:
                rooms[str(to)] = {"title": graph[to]["title"], "exits": [],
                                  "flags": ["ghost"], "hazards": []}
            links.append({"from": str(v), "dir": d, "to": str(to),
                          "ghost": True})
    trail = [{"from": str(a), "dir": d, "to": str(b)} for d, a, b in l.trail]
    pos = str(l.position) if l.position is not None else None
    return rooms, links, trail, pos


def read_state(data_dir):
    """Adapt the play-mud store into the visualizer contract."""
    store = _load_json(os.path.join(data_dir, ".mud_memory.json")) or {}
    plan_raw = _load_json(os.path.join(data_dir, "plan.json")) or {}

    rooms, links = {}, []
    for key, r in (store.get("rooms") or {}).items():
        exits = [DIRECTIONS.get(e.strip("()").lower(), e.strip("()").lower())
                 for e in (r.get("exits") or "").split()]
        hazards = r.get("hazards") or []
        flags = []
        if any("death" in h for h in hazards):
            flags.append("death")
        if hazards:
            flags.append("hazard")
        rooms[key] = {"title": key, "exits": exits, "flags": flags,
                      "hazards": hazards}
        for d, dest in (r.get("links") or {}).items():
            links.append({"from": key, "dir": d, "to": dest})

    # peeks (`exits` output) -> ghost rooms: known by name, never visited
    for key, r in (store.get("rooms") or {}).items():
        for d, dest in (r.get("peeks") or {}).items():
            if d in (r.get("links") or {}):
                continue  # already walked
            if dest not in rooms:
                rooms[dest] = {"title": dest, "exits": [], "flags": ["ghost"],
                               "hazards": []}
            if "ghost" in rooms[dest]["flags"]:
                links.append({"from": key, "dir": d, "to": dest, "ghost": True})

    trail = []
    for t in store.get("trail") or []:
        m = TRAIL_RE.match(t)
        if m and "(darkness)" not in m.group(3):
            trail.append({"from": m.group(2), "dir": m.group(1), "to": m.group(3)})

    char = store.get("char") or {}
    vitals = {"level": _int(char.get("level")), "gold": _int(char.get("gold")),
              "xp": _int(char.get("xp")), "xp_to_next": _int(char.get("xp_to_next")),
              "max_hp": _int(char.get("max_hp")),
              "max_mana": _int(char.get("max_mana")),
              "max_moves": _int(char.get("max_moves")),
              "hp": None, "mana": None, "moves": None}
    try:
        with open(os.path.join(data_dir, "player.md")) as f:
            m = VITALS_RE.search(f.read())
        if m:
            vitals.update(hp=int(m.group(1)), mana=int(m.group(2)),
                          moves=int(m.group(3)))
    except OSError:
        pass

    plan = None
    if plan_raw.get("goal") or plan_raw.get("subtasks"):
        plan = {"goal": plan_raw.get("goal", ""),
                "steps": [{"text": s.get("text", ""), "check": s.get("check"),
                           "done": bool(s.get("done"))}
                          for s in plan_raw.get("subtasks") or []]}

    state = {"rooms": rooms, "links": links, "trail": trail,
             "position": store.get("current_room"),
             "vitals": vitals, "deaths": int(store.get("deaths") or 0),
             "events": store.get("events") or [],
             "plan": plan, "thought": store.get("thought") or "",
             "conditions": store.get("conditions") or [],
             "thought_age_s": _thought_age(store)}
    # prefer the agent's live narration when it's fresher than a voiced thought
    n_text, n_age = latest_narration(Handler.cc_dir)
    if n_text and (state["thought_age_s"] is None or n_age < state["thought_age_s"]):
        state["thought"], state["thought_age_s"] = n_text, n_age
    if Handler.world is not None:
        # exact map from the true-world localizer replaces the title-keyed one
        w_rooms, w_links, w_trail, w_pos = world_map()
        state.update(rooms=w_rooms, links=w_links, trail=w_trail,
                     position=w_pos)
    state.update(derive_activity(Handler.transcript, state["position"],
                                 data_dir))
    return state


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _thought_age(store):
    import time
    at = store.get("thought_at")
    if not at or not store.get("thought"):
        return None
    return max(0, int(time.time() - at) // 15 * 15)  # quantized vs hash churn


# --- narration harvest: the playing agent's own commentary -------------------
# The agent narrates its reasoning in its Claude Code responses; Claude Code
# stores the session locally as JSONL. Tailing it gives us the live "thinking"
# without asking the model to double-report anything.

def _find_cc_project_dir():
    import glob as g
    cands = g.glob(os.path.expanduser("~/.claude/projects/*02*agent*skills*"))
    return max(cands, key=os.path.getmtime) if cands else None


def _parse_ts(ts):
    import calendar
    import time as t
    try:
        return calendar.timegm(t.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return None


def latest_narration(cc_dir):
    """(text, age_seconds) of the newest assistant remark in the session log."""
    import glob as g
    import time
    if not cc_dir:
        return None, None
    files = g.glob(os.path.join(cc_dir, "*.jsonl"))
    if not files:
        return None, None
    path = max(files, key=os.path.getmtime)
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 150000))
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return None, None
    best = None
    for line in data.split("\n"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") != "assistant":
            continue
        content = (o.get("message") or {}).get("content") or []
        texts = [c.get("text", "") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        text = " ".join(t for t in texts if t).strip()
        if text:
            best = (text, o.get("timestamp"))
    if not best:
        return None, None
    text, ts = best
    if len(text) > 220:
        text = text[:217].rstrip() + "…"
    at = _parse_ts(ts) or os.path.getmtime(path)
    age = max(0, int(time.time() - at) // 15 * 15)
    return text, age


# --- OpenAI TTS (optional) ---------------------------------------------------
# Configured via ./.env (git-ignored):  OPENAI_API_KEY=sk-...
# Optional:  TTS_VOICE=nova   TTS_MODEL=tts-1
TTS_CACHE = os.path.join(HERE, ".tts_cache")


def load_env():
    cfg = {}
    for name in (".env", ".env.local"):     # .local wins, per Vite convention
        try:
            with open(os.path.join(HERE, name)) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip()
        except OSError:
            pass
    return cfg


def tts_synthesize(text):
    """Text -> mp3 bytes via OpenAI, with an on-disk cache (repeats are free)."""
    import urllib.request
    cfg = Handler.env
    key = cfg.get("OPENAI_API_KEY")
    if not key:
        return None
    os.makedirs(TTS_CACHE, exist_ok=True)
    cache = os.path.join(
        TTS_CACHE, hashlib.sha1(text.encode()).hexdigest() + ".mp3")
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return f.read()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps({
            "model": cfg.get("TTS_MODEL", "tts-1"),
            "voice": cfg.get("TTS_VOICE", "nova"),
            "input": text[:400],
            "response_format": "mp3",
        }).encode(),
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    audio = urllib.request.urlopen(req, timeout=20).read()
    with open(cache, "wb") as f:
        f.write(audio)
    return audio


class Handler(BaseHTTPRequestHandler):
    data_dir = DEFAULT_DATA
    transcript = DEFAULT_TRANSCRIPT
    world = None  # WorldTracker when world files are available
    cc_dir = None  # Claude Code project dir of the playing session
    env = {}      # ./.env contents

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/speak":
            text = parse_qs(url.query).get("text", [""])[0].strip()
            try:
                audio = tts_synthesize(text) if text else None
            except Exception:
                audio = None
            if audio:
                self._send(200, audio, "audio/mpeg")
            else:
                self._send(503, b"tts unavailable", "text/plain")
            return
        if url.path == "/state":
            state = read_state(self.data_dir)
            state["tts"] = bool(Handler.env.get("OPENAI_API_KEY"))
            payload = json.dumps(state, sort_keys=True).encode()
            h = hashlib.sha1(payload).hexdigest()[:16]
            if parse_qs(url.query).get("hash", [""])[0] == h:
                self._send(200, b'{"unchanged": true}', "application/json")
                return
            state["hash"] = h
            self._send(200, json.dumps(state).encode(), "application/json")
            return
        # static: dist/
        rel = url.path.lstrip("/") or "index.html"
        path = os.path.normpath(os.path.join(DIST, rel))
        if not path.startswith(DIST) or not os.path.isfile(path):
            path = os.path.join(DIST, "index.html")  # SPA fallback
        if not os.path.isfile(path):
            self._send(503, b"UI not built. Run: npm install && npm run build",
                       "text/plain")
            return
        ctype = {"html": "text/html", "js": "text/javascript",
                 "css": "text/css", "svg": "image/svg+xml",
                 "map": "application/json"}.get(path.rsplit(".", 1)[-1],
                                                "application/octet-stream")
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        # empty dir -> empty contract, no crash
        s = read_state(d)
        assert s["rooms"] == {} and s["position"] is None and s["plan"] is None
        # populated fixture in the skill's store shape
        with open(os.path.join(d, ".mud_memory.json"), "w") as f:
            json.dump({
                "rooms": {
                    "A Room": {"exits": "n e (s)", "links": {"north": "B Room"},
                               "peeks": {"north": "B Room", "east": "C Room"},
                               "here": [], "hazards": ["darkness through east"]},
                    "B Room": {"exits": "s u", "links": {}, "here": [],
                               "hazards": ["a death occurred here"]},
                },
                "char": {"level": "3", "gold": "42", "xp": "500",
                         "xp_to_next": "1500", "max_hp": "48"},
                "events": ["Killed a rat (+10 xp)"], "current_room": "A Room",
                "trail": ["north: A Room → B Room", "east: A Room → (darkness)"],
                "deaths": 1,
            }, f)
        with open(os.path.join(d, "player.md"), "w") as f:
            f.write("## Vitals\nHP 21 · Mana 100 · Moves 85  (max 21/100/85)\n")
        with open(os.path.join(d, "plan.json"), "w") as f:
            json.dump({"goal": "win", "subtasks": [
                {"text": "step", "check": "level>=3", "done": False}]}, f)
        s = read_state(d)
        assert s["rooms"]["A Room"]["exits"] == ["north", "east", "south"]
        assert s["rooms"]["A Room"]["flags"] == ["hazard"]
        assert s["rooms"]["B Room"]["flags"] == ["death", "hazard"]
        assert s["rooms"]["B Room"]["exits"] == ["south", "up"]
        assert {"from": "A Room", "dir": "north", "to": "B Room"} in s["links"]
        # peeked-not-walked destination became a ghost room + ghost link;
        # the already-walked peek (north) did not duplicate
        assert s["rooms"]["C Room"]["flags"] == ["ghost"]
        assert {"from": "A Room", "dir": "east", "to": "C Room",
                "ghost": True} in s["links"]
        assert len([l for l in s["links"] if l["to"] == "B Room"]) == 1
        assert s["trail"] == [{"from": "A Room", "dir": "north", "to": "B Room"}]
        assert s["vitals"]["hp"] == 21 and s["vitals"]["level"] == 3
        assert s["vitals"]["max_hp"] == 48 and s["vitals"]["moves"] == 85
        assert s["position"] == "A Room" and s["deaths"] == 1
        assert s["plan"]["steps"][0]["check"] == "level>=3"
        # activity derivation from a transcript fixture
        tpath = os.path.join(d, "transcript.log")
        with open(tpath, "w") as f:
            f.write("[SENT] kill rat\nYou hit the rat hard.\n"
                    "The rat misses you.\n")
        old = Handler.transcript
        Handler.transcript = tpath
        try:
            s = read_state(d)
            assert s["activity"]["kind"] == "fighting", s["activity"]
            assert s["combat"]["foe"] == "rat"
            assert any("You hit the rat" in l for l in s["combat"]["lines"])
            with open(tpath, "a") as f:
                f.write("The rat is dead!  R.I.P.\n[SENT] rest\nYou rest.\n")
            s = read_state(d)
            assert s["activity"]["kind"] == "resting", s["activity"]
            assert s["combat"] is None
            assert any("R.I.P." in l for l in s["feed"])
        finally:
            Handler.transcript = old
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA,
                    help="play-mud data dir (default: %(default)s)")
    ap.add_argument("--transcript", default=DEFAULT_TRANSCRIPT,
                    help="play-mud session transcript (default: %(default)s)")
    ap.add_argument("--world", default=DEFAULT_WORLD,
                    help="server .wld dir for the exact map; 'off' disables "
                         "(default: %(default)s)")
    ap.add_argument("--cc", default="auto",
                    help="Claude Code project dir to harvest the playing "
                         "agent's narration from; 'auto' to locate, 'off' "
                         "to disable")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    Handler.data_dir = os.path.abspath(args.data)
    Handler.transcript = os.path.expanduser(args.transcript)
    Handler.env = load_env()
    print("TTS: %s" % ("OpenAI (%s / %s)" % (
        Handler.env.get("TTS_MODEL", "tts-1"),
        Handler.env.get("TTS_VOICE", "nova"))
        if Handler.env.get("OPENAI_API_KEY") else "browser fallback (no .env key)"))
    if args.cc != "off":
        Handler.cc_dir = args.cc if args.cc != "auto" else _find_cc_project_dir()
        print("narration harvest: %s" % (Handler.cc_dir or "no session dir found"))
    if args.world != "off" and os.path.isdir(args.world):
        from world import WorldTracker
        Handler.world = WorldTracker(args.world, Handler.transcript)
        print("world mode: %d rooms loaded from %s"
              % (len(Handler.world.graph), args.world))
    else:
        print("world mode OFF — falling back to the agent's own map")
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("MUD Observatory: http://127.0.0.1:%d  (data: %s)"
          % (args.port, Handler.data_dir))
    print("Demo mode:       http://127.0.0.1:%d/?demo=1" % args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
