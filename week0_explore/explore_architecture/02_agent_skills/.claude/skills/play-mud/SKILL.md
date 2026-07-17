---
name: play-mud
description: Play the tbaMUD/CircleMUD game server running at localhost:4000 (telnet) as the character "dummy". Use this skill whenever the user asks to play, explore, or test the MUD, interact with the game world, move around Midgaard, fight monsters, check stats or inventory, or mentions "the mud", "telnet localhost 4000", tbaMUD, or CircleMUD. Always use the bundled session scripts instead of raw telnet/nc/python one-offs — they own the connection, login, prompt detection, and ANSI stripping.
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

python3 $SKILL/scripts/mud_session.py start      # connect + full login, prints the room
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
| `status` | Session alive? Shows last prompt (your HP/mana/moves) and transcript path. |
| `log [-n N]` | Tail the full session transcript (everything seen + `[SENT]` lines). Useful to re-read something that scrolled by. |
| `stop` | Send `quit` to the game and shut the daemon down. |

One game command per `cmd` call. The exit status and stderr warn you if no
prompt was seen (partial output) or the server dropped the connection.

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
