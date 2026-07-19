# Plan: realtime MUD observatory

## Goal

A local web dashboard for watching an agent play the MUD: the map growing
room by room, the agent's position, vitals, plan, live activity (fighting /
resting / shopping / thinking), the actual combat text, and the agent's own
running commentary — optionally spoken aloud. Zero model involvement and zero
tokens: it is a pure observer that renders what the play session already
produces on disk.

Full run/architecture docs live in `week0_explore/visualizer/README.md`;
this file records scope and the decisions that shaped it.

## Architecture

- `serve.py` (stdlib Python) serves the built UI plus one endpoint, `/state`:
  a single JSON contract (rooms, links, trail, position, vitals, events,
  plan, activity, combat, feed, thought). The UI knows only this contract;
  every assumption about the skill's file formats is isolated in the
  server-side reader, so a differently-implemented skill (or the week 1/2
  loop) only needs a new reader — the front end never changes.
- UI: Vite + React + TypeScript + Tailwind + d3-zoom + framer-motion. Node is
  a dev-time dependency only — `dist/` is committed, running needs only
  `python3 serve.py`. The page polls at 1 Hz with a content hash, so it
  re-renders only on change.
- Watchability is a requirement, not polish: rooms materialize, the camera
  glides after a pulsing agent marker, frontier exits breathe, recent moves
  leave a fading trail, hazards glow, vitals animate with state colors,
  events slide in color-coded, LEVEL UP banners and a death vignette flash,
  and a demo mode (`?demo=1`) exercises every visual with no game running.

## Decisions

- **2026-07-18 — framework upgrade.** Started as "no framework, no build
  step"; upgraded to the React stack when it became plausible this grows into
  the single interface for weeks 1–2. Runtime stayed Python-only via the
  committed build.
- **2026-07-18 — activity layer.** Position alone wasn't watchable: long
  stationary periods were illegible. The server now tails the session
  transcript and *derives* what the agent is doing (fighting — with the real
  combat lines in a docked panel — resting, shopping, reading, thinking,
  corpse-run), plus a raw terminal drawer. No agent cooperation needed.
- **2026-07-18 — world mode (the observer may know the world).** The playing
  agent stays discovery-based, but the visualizer is not the player: it
  parses the tbaMUD server's own `.wld` files and *localizes* the agent by
  replaying its transcript against the true room graph (belief-set narrowing,
  with backfill once ambiguity collapses). This gives exact room identity —
  five same-titled "Main Street" segments stay five distinct nodes, which
  title-based identity cannot do — plus truthful ghost previews of unvisited
  neighbors. `--world off` falls back to the agent's own memory-keyed map.
- **2026-07-18 — narration harvest.** The agent narrates richly in its own
  Claude Code responses but rarely duplicates that into a side channel.
  Instead of demanding double-reporting, the server tails the session's local
  JSONL and lifts the latest assistant remark into the caption (with age
  display; a deliberate `thought` subcommand still exists and wins when
  fresher). Principle: harvest what the agent already produces rather than
  asking it to remember to report.
- **2026-07-19 — neural voice.** Browser TTS proved robotic; `/speak` now
  proxies OpenAI TTS (key in git-ignored `.env.local`, on-disk audio cache,
  silent fallback to browser TTS when unconfigured). Speech never queues
  (newest line replaces current), never repeats within 30 s, and prioritizes
  deaths and level-ups over commentary.

## Later, not now

XP sparkline, a command box injecting into the daemon's control socket,
replay/scrubbing of a past session from its transcript, multi-session
comparison.

## Location

`week0_explore/visualizer/`, self-contained; nothing else in the repo depends
on it. Whether it moves into week 1/2 or stays standalone is decided when
those weeks take shape.
