# claude-code-camp-2026-Q2

A Player Journey Agent for tbaMUD: an AI agent that plays a text MUD like a
real player, maps the world, tracks its progression, and reports where
players get confused, blocked, bored or overpowered.

## Why

Game studios lose players to friction they cannot see. An agent that
actually plays the game surfaces the journey a new player lives: where it
gets lost, what kills it, when it gets bored. tbaMUD (CircleMUD) is the
proving ground before the agent faces a private game world.

## How it is built

Before building we tested the agent architecture levels bottom-up: a plain
agent file, then agent skills with bundled scripts. The experiments and
conclusions are in [docs/explore_architectures.md](docs/explore_architectures.md),
the weekly journal in [docs/journal/](docs/journal/). The direction they
set: everything moved from the model into code became dependable even on a
small model, so the final agent runs on a custom agentic loop built during
the two camp weeks.

## Getting started

Run the MUD server (Docker required):

    cd week0_explore/infrastructure
    docker compose up -d

The game is then live on `telnet localhost 4000`.

## Structure

- `week0_explore/` — MUD infrastructure, exploration notes, architecture
  experiments, the play-mud skill
- `week1_baseline/` — first working agent (week 1)
- `week2_capable/` — the capable agent (week 2)
- `docs/` — technical documentation and the weekly journal

## Status

Pre-week complete: architectures explored, direction chosen. Weeks 1 and 2
build the agent.
