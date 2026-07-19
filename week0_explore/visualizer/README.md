# MUD Observatory

A live web dashboard for **watching an agent play the MUD**: the map grows
room by room as the agent explores, with its position, vitals, plan, combat,
events, and running commentary — optionally spoken aloud.

It is a pure **observer**: it only reads files the play session already
produces. It never talks to the game server, never writes to the agent's
memory, and the playing agent doesn't know it exists.

## Run

```bash
python3 serve.py            # → http://127.0.0.1:8790
```

Python 3 stdlib only — Node is **not** needed to run (the built UI in `dist/`
is committed). Useful flags:

| Flag | Default | Purpose |
|---|---|---|
| `--data <dir>` | `../explore_architecture/02_agent_skills/data` | the play-mud memory dir to watch |
| `--transcript <file>` | `~/.play_mud/localhost_4000/transcript.log` | session transcript (activity + world replay) |
| `--world <dir>` \| `off` | `../infrastructure/lib/world/wld` | server world files for the exact map |
| `--cc <dir>` \| `auto` \| `off` | `auto` | Claude Code project dir to harvest narration from |
| `--port <n>` | `8790` | HTTP port |
| `--selftest` | — | run the adapter/localizer test suite |

**Demo mode** — no game or agent needed: open `http://127.0.0.1:8790/?demo=1`
for a scripted session that exercises every visual (growth, combat, death,
level-up, darkness, plan progress).

## What it reads (the dependencies)

All inputs come from the **play-mud skill**
(`../explore_architecture/02_agent_skills/.claude/skills/play-mud/`) and its
runtime side effects:

| Source | Written by | Feeds |
|---|---|---|
| `<data>/.mud_memory.json` | skill daemon (real time) | vitals, events, deaths, thought |
| `<data>/plan.json` | skill CLI (`plan`, `persona`) | plan panel, persona |
| `<data>/player.md` | skill daemon | live HP/mana/moves line |
| `~/.play_mud/<host>_<port>/transcript.log` | skill daemon | activity badge, combat panel, terminal feed, **world-mode map replay** |
| `infrastructure/lib/world/wld/*.wld` | the tbaMUD server's own world | exact room graph (vnums) |
| `~/.claude/projects/<02_agent_skills>/*.jsonl` | Claude Code | the agent's narration (caption + voice) |
| `.env.local` (git-ignored) | you | `OPENAI_API_KEY`, `TTS_VOICE`, `TTS_MODEL` for neural voice; absent → browser TTS |

If a source is missing, the related feature degrades silently (empty map →
"waiting for first data…", no key → browser voice, `--world off` → the map
falls back to the agent's own title-keyed memory).

## How it works

```
serve.py     stdlib HTTP server
 ├─ /state   adapter: merges the sources above into one JSON contract,
 │           content-hashed so the page only re-renders on change
 ├─ /speak   OpenAI TTS proxy with on-disk cache (.tts_cache/)
 └─ static   serves dist/ (the built React app)

world.py     the "omniscient observer" layer
 ├─ parses the server's .wld files into a room graph (vnum → title, exits)
 └─ Localizer: replays the transcript, tracking a belief-set of candidate
    vnums per observation; movements narrow it, collapses record exact
    visited rooms/edges — this keeps five same-titled "Main Street"
    segments apart, which title-based identity cannot

src/         React + TS + Tailwind + d3-zoom + framer-motion (Vite)
 ├─ state.ts        contract types + 1s poller + demo engine (demo.ts)
 ├─ map/layout.ts   grid layout: BFS from first room, collision spiral,
 │                  floating clusters for unlinked rooms
 ├─ map/MapView.tsx SVG map: rooms materialize, camera follows the agent,
 │                  frontier stubs, ghost rooms, trail, hazards, tooltips
 ├─ cockpit/        vitals bars, stat tiles, XP bar, plan checklist,
 │                  event feed, heartbeat, narration caption
 └─ overlays.tsx    combat panel, terminal drawer, toasts, voice engine
```

Design rule: the UI knows **only the `/state` contract** — the adapter
absorbs all knowledge of the skill's file formats. Week 1/2 loops can either
write contract-shaped state directly or swap the reader functions in
`serve.py`; the page never changes.

The playing agent stays **discovery-based** — the true world files inform the
observer's map only. Nothing here feeds knowledge back to the agent.

## Developing the UI

```bash
npm install
npm run dev      # Vite dev server (proxies /state to :8790)
npm run build    # → dist/  (commit it: runtime stays Node-free)
```

After changing `serve.py` or `world.py`, restart the server. After changing
`src/`, rebuild — `dist/` is served per-request, a browser refresh suffices.
