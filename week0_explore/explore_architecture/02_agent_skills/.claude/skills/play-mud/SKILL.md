---
name: play-mud
description: Play the tbaMUD/CircleMUD game server running at localhost:4000 (telnet) as the character "dummy", with persistent memory (data/player.md, data/world.md) that supports long-term goals like reaching a level or hunting specific monsters across sessions. Use this skill whenever the user asks to play, explore, or test the MUD, interact with the game world, move around Midgaard, fight monsters, level up, check stats or inventory, or mentions "the mud", "telnet localhost 4000", tbaMUD, or CircleMUD. Always use the bundled session scripts instead of raw telnet/nc/python one-offs — they own the connection, login, prompt detection, ANSI stripping, and memory upkeep.
---

# Playing the MUD

This skill drives one **persistent** game session through `scripts/mud_session.py`.
A background daemon holds the telnet connection; every `cmd` call talks to the
same live session. Never open your own telnet/nc connection — a second login
would kick or duplicate the character, and raw telnet needs fixed sleeps and
manual ANSI handling that the script already solves.

## Quick start

```bash
SKILL=path/to/play-mud            # this skill's directory

python3 $SKILL/scripts/mud_session.py start      # connect + full login, prints room + goals
python3 $SKILL/scripts/mud_session.py memory     # read player.md + world.md BEFORE acting
python3 $SKILL/scripts/mud_session.py goal "reach level 7"   # pin the long-term goal
python3 $SKILL/scripts/mud_session.py cmd look   # send a command, get the clean response
python3 $SKILL/scripts/mud_session.py stop       # quit the game cleanly when done
```

`start` handles the entire login (name → password → MOTD → menu → enter game)
and returns once the in-game prompt `<hp>H <mana>M <moves>V ... >` is seen.
Responses are read **until the prompt appears**, not for a fixed time, and are
returned with ANSI color codes and telnet negotiation stripped. Long output
("*** Press return ***" pager) is auto-continued and returned in full.

## Command reference

| Command | What it does |
|---|---|
| `start` | Connect, log in end to end, daemonize. Fails clearly if the server is down, the password is wrong, or a session already runs. |
| `cmd <words...> [--timeout N]` | Send **one** game command, print everything up to the next prompt. Async output that arrived earlier (chat, combat ticks) is included first. |
| `recv [--wait N]` | Collect output that arrives *without* sending anything — use after starting a fight, or to wait for slow events. Default 1.5s. |
| `status` | Session alive? Last prompt (HP/mana/moves), current room, rooms mapped, goals. |
| `log [-n N]` | Tail the full session transcript (everything seen + `[SENT]` lines). Useful to re-read something that scrolled by. |
| `stop` | Send `quit` to the game and shut the daemon down. |
| `goal "<text>"` | Record a long-term goal in `data/player.md` (e.g. `goal "reach level 7"`). |
| `memory` | Print both memory files — the quickest way to load them into context. |

One game command per `cmd` call. The exit status and stderr warn you if no
prompt was seen (partial output) or the server dropped the connection.

## Memory — how to pursue long-term goals

The daemon maintains two files in `./data/` (relative to where the session was
started), **updating them in real time as game output arrives** — you never
need to take notes yourself:

- `data/player.md` — your goals & notes (a section that is never
  auto-overwritten), live vitals, character sheet from the last `score`,
  current location, and recent events (kills with XP, level-ups, deaths).
- `data/world.md` — an auto-built map: every room seen, its exits, what was
  in it, and the observed connections between rooms (`south → Market Square`).

Memory persists across sessions (state in `data/.mud_memory.json`), which is
what makes multi-session goals — "reach level 8", "find and kill the beastly
fido" — feasible: you resume with the map and history instead of rediscovering
the world.

The loop that makes this work:

1. **Start of session**: run `memory` (or read both files) before your first
   move — it tells you where you are, what you were doing, and what's left.
2. **Set the goal down**: `goal "defeat the cityguard"` — a goal that lives
   only in your head is lost when the session ends.
3. **Before each decision**, check the memory instead of re-exploring:
   world.md answers "how do I get back to the shop?", player.md answers
   "can I win this fight?" (vitals) and "what just happened?" (events).
4. **Record insights** the tracker can't see (e.g. "cityguard too strong at
   level 6", "grocer is 2s 1w from temple") by editing the *Goals & notes*
   section of `data/player.md` — everything below the AUTO marker is
   machine-rewritten, so keep your notes above it.

## Playing well

- **Orient first**: after `start`, run `cmd look`, `cmd score`, `cmd inventory`,
  `cmd equipment` to know where you are and what you have.
- **The prompt is your health bar**: `90H 100M 92V >` = hit points, mana,
  movement. Watch H during fights; `cmd flee` if it drops fast.
- **Combat is asynchronous**: `cmd kill <target>` returns the first round;
  follow with `recv --wait 3` repeatedly to watch rounds until the fight ends.
- **Sizing up**: `cmd consider <target>` before attacking tells you if a fight
  is winnable.
- **Movement**: `cmd n` / `s` / `e` / `w` / `u` / `d`; `cmd exits` lists ways out.
- **Recovery**: `cmd rest` or `cmd sleep` to regain H/M/V faster, `cmd stand`
  / `cmd wake` to get up.
- For a broader command cheat sheet (items, shops, communication, info),
  read [references/gameplay.md](references/gameplay.md).

## Session facts

- Server: tbaMUD 2025 (CircleMUD-derived) at `localhost:4000`.
- Character: `dummy` / password `helloworld` (baked into the script; override
  with `MUD_HOST`, `MUD_PORT`, `MUD_USER`, `MUD_PASS` env vars if needed).
- Session state (control socket, transcript, daemon log) lives in
  `~/.play_mud/<host>_<port>/`.
- Memory files live in `./data/` under the directory `start` was run from
  (override with `MUD_MEMORY_DIR`) — so run all subcommands from the same
  working directory.
- Start location: The Temple Of Midgaard.

## Troubleshooting

- **"No active MUD session"** — the daemon isn't running (never started, or it
  exited when the server dropped the link). Run `start` again; the game resumes
  where the character was.
- **"A session is already running"** — just use `cmd`; or `stop` first for a
  fresh login.
- **`cmd` warns "no prompt within Ns"** — the command produced slow or paged
  output; run `recv --wait 3` to collect the rest, or retry with `--timeout 15`.
- **Server down** — `start` reports it cannot reach `localhost:4000`; nothing
  to do but start the MUD server.
- **What actually happened?** — `log -n 100` replays the raw session history.
