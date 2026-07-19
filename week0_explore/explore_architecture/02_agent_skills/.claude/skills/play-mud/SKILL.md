---
name: play-mud
description: Play the tbaMUD/CircleMUD game server running at localhost:4000 (telnet) as the character "dummy", with persistent memory (data/player.md, data/world.md), script-managed plans with verifiable conditions, and a persona-driven play method — built for long-term goals like reaching a level or defeating a specific monster across sessions. Use this skill whenever the user asks to play, explore, or test the MUD, interact with the game world, fight monsters, level up, pursue a quest, check stats or inventory, or mentions "the mud", "telnet localhost 4000", tbaMUD, or CircleMUD. Always use the bundled session scripts instead of raw telnet/nc/python one-offs — they own the connection, login, prompt detection, ANSI stripping, and memory upkeep.
---

# Playing the MUD

This skill drives one **persistent** game session through `scripts/mud_session.py`.
A background daemon holds the telnet connection; every `cmd` call talks to the
same live session. Never open your own telnet/nc connection — a second login
would take over the character, and raw telnet needs fixed sleeps and manual
ANSI handling that the script already solves.

## Quick start

```bash
SKILL=path/to/play-mud            # this skill's directory

python3 $SKILL/scripts/mud_session.py start      # login; prints persona, plan, notes
python3 $SKILL/scripts/mud_session.py memory     # read player.md + world.md BEFORE acting
python3 $SKILL/scripts/mud_session.py cmd look   # send a command, get the clean response
python3 $SKILL/scripts/mud_session.py stop       # quit the game cleanly when done
```

`start` handles the entire login end to end and returns once the in-game
prompt `<hp>H <mana>M <moves>V ... >` is seen. Responses are read **until the
prompt appears**, not for a fixed time, ANSI-stripped, and the pager
("*** Press return ***") is auto-continued.

## Command reference

| Command | What it does |
|---|---|
| `start` | Connect, log in, daemonize. Prints memory summary, persona, and current plan step. |
| `cmd <words...> [--timeout N]` | Send **one** game command, print everything up to the next prompt. |
| `recv [--wait N]` | Collect output that arrives *without* sending anything — combat rounds, slow events. |
| `status` | Alive? Vitals, room, rooms mapped, persona, **current plan step + condition check**. |
| `plan set "<goal>"` | Set the long-term goal (clears subtasks). |
| `plan add "<step>" [--check "<cond>"]` | Append an ordered subtask, optionally with a verifiable condition. |
| `plan done` | Mark the current subtask done and advance. Reflect when you do. |
| `plan show` | The whole plan with a live evaluation of the current condition. |
| `persona "<style>"` | Set the play style (risk appetite, exploration style) to apply everywhere. |
| `find <terms>` | Search all memory: rooms, links, shops, signs, hazards, events, notes, transcript. |
| `goal "<note>"` | Append a free-form insight/note to player.md (the reflection tool). |
| `thought "<one line>"` | Voice your current intent (shown live to anyone observing the session). |
| `memory` | Print both memory files — the quickest way to load them into context. |
| `log [-n N]` | Tail the raw session transcript. |
| `stop` | Quit the game and shut the daemon down. |

**Plan conditions** the tracker can verify from game state: `level>=N`,
`gold>=N`, `xp>=N`, `hp>=N`, `mana>=N`, `moves>=N` (any of `>= <= > < =`),
`item:<substring>` (carrying it, per last `inventory`), `room:<substring>`
(current location). The current step and any unmet condition are surfaced in
every `status` and session start, so a plan violation is visible the moment it
exists — check `status` after anything that could change your state.

## Memory — what the daemon records for you

Two files in `./data/` (relative to where the session was started), updated
**in real time as game output arrives** — never take notes manually on things
the tracker already records:

- `data/player.md` — your notes (never auto-overwritten), persona, plan with
  live condition checks, live vitals, character sheet, **computed signals**
  (XP per kill, implied fights to next level, movement and gold trends,
  deaths), carried items, recent events.
- `data/world.md` — the map: rooms, exits, observed links, **shop stock**
  (recorded whenever you `list` in a shop), **sign/notice texts** (recorded
  whenever you `read`/`examine` something), **hazard marks** (⚠ darkness,
  deaths), a **frontier** of untried exits, and the trail of recent moves.

Memory persists across sessions (`data/.mud_memory.json`), so multi-session
goals resume with the map and history instead of rediscovering the world.

## The play method

The skill records information; winning comes from *reasoning over it*. Apply
the persona to every choice below — a cautious persona flees earlier, probes
shallower, and banks gold; a bold one accepts thinner margins.

1. **Gather information early and cheaply.** `look` at things, `read` every
   sign, `list` in every shop, `consider` before every fight, `inventory`
   after every change — and run `cmd exits` in each new room: it names every
   destination without walking there, and the tracker records those names on
   the map (world.md shows them as `⇢ unvisited`), so you navigate by name
   instead of blindly. Each of these costs almost nothing and lands in memory
   permanently — the value compounds. An unread sign is a future dead end.
2. **When blocked, correlate memory before improvising.** Stuck at a locked
   door, a dark passage, a too-strong monster? `find key`, `find lamp`,
   `find <monster>` — the solution has often already scrolled past you: an
   item in a shop's stock, a hint on a sign, a room you saw but didn't enter.
   Only after memory comes up empty should you go looking for new information.
3. **Treat obstacles as having acquirable solutions.** Games place solutions
   before problems: darkness implies a light source exists, a locked door
   implies a key or command, an unbeatable enemy implies leveling or better
   gear. Convert the obstacle into a plan step with a check
   (`plan add "get a light source" --check "item:lamp"`) instead of retrying
   the blocked path.
4. **Watch the signals and adapt.** The Signals block in player.md is your
   dashboard: XP-per-kill falling means your targets are outleveled — hunt
   elsewhere; a huge implied-fights count means grinding here is the wrong
   strategy; moves trending down means rest before exploring; gold flat means
   you can't buy your way past the next obstacle yet.
5. **Run cheap experiments first.** Prefer reversible probes to commitments:
   `consider` before `kill`, one step into the unknown before a deep run, one
   cheap purchase before outfitting. When an experiment fails, its result is
   in memory — don't repeat it, and note it (`goal "..."`) if the tracker
   couldn't see why.
6. **Manage movement and gold as budgets.** Every step costs moves; getting
   stranded at 0V is a real failure mode. Plan routes with the map instead of
   wandering, keep a reserve for the way back, and spend gold against plan
   checks, not impulse. And remember: **carried gold dies with you** — it goes
   into your corpse. Bank the surplus at an ATM/bank (`deposit <n>`; your map
   remembers where — `find atm`) whenever you're holding more than shopping
   money, and always before entering dangerous territory.
7. **Reflect at each plan step.** When you `plan done`, spend one moment:
   what did this step teach? Record it with `goal "..."` if the tracker
   couldn't have seen it. If your approach keeps failing, change the persona,
   not just the tactic.
8. **Narrate your intent.** Whenever your intention changes — new target, new
   destination, a retreat, a purchase — voice it first in one line:
   `thought "hunting rats until level 3"`. Like a pilot calling maneuvers,
   this makes the session observable from outside (a live map watches it);
   your reasoning otherwise exists nowhere but in your head.

## Mechanics worth knowing

- **The prompt is your health bar**: `90H 100M 92V >` = hit points, mana,
  movement. Watch H during fights; flee early per your persona.
- **Combat is asynchronous**: `cmd kill <target>` returns the first round;
  poll `recv --wait 3` to watch rounds until it ends.
- **While resting, poll `cmd score` every 20–30s** — vitals only update when
  the game prints a prompt, so this is how you (and anyone observing) see HP
  climb and know when you're fit to continue.
- **Kills are auto-looted**: `start` enables the game's `autoloot`/`autogold`
  toggles, so corpses empty into your inventory. Still check `inventory`
  after fights and grab floor items — loot funds everything you buy.
- **Death** drops your corpse (with gear) where you died; you respawn at the
  starting temple. The death is logged as an event and a ⚠ hazard on the room.
- For the game's command vocabulary (movement, items, shops, communication),
  read [references/gameplay.md](references/gameplay.md). Beyond that, **the
  game documents itself**: `cmd commands` lists everything, `cmd help <x>`
  explains it — consult them instead of guessing syntax.

## Session facts

- Server: tbaMUD 2025 (CircleMUD-derived) at `localhost:4000`.
- Character: `dummy` / password `helloworld` (baked into the script; override
  with `MUD_HOST`, `MUD_PORT`, `MUD_USER`, `MUD_PASS` env vars if needed).
- Session state (control socket, transcript, daemon log) lives in
  `~/.play_mud/<host>_<port>/`.
- Memory files live in `./data/` under the directory `start` was run from
  (override with `MUD_MEMORY_DIR`) — so run all subcommands from the same
  working directory.

## Troubleshooting

- **"No active MUD session"** — the daemon isn't running (never started, or it
  exited when the server dropped the link). Run `start` again; the game and
  the memory resume where they were.
- **"A session is already running"** — just use `cmd`; or `stop` first for a
  fresh login.
- **`cmd` warns "no prompt within Ns"** — slow or paged output; run
  `recv --wait 3` to collect the rest, or retry with `--timeout 15`.
- **Position shows "(unknown)"** — you walked into darkness; memory can't map
  what you can't see. Get or light a light source, or retrace via the trail.
- **Server down** — `start` reports it cannot reach `localhost:4000`.
- **What actually happened?** — `log -n 100` replays raw history; `find <term>`
  searches everything ever seen.
