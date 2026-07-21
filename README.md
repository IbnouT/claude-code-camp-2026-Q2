# claude-code-camp-2026-Q2

A Player Journey Agent for tbaMUD: an AI agent that plays a text MUD like a
real player, maps the world, tracks its progression, and reports where players
get confused, blocked, bored or overpowered.

## Why

Game studios lose players to friction they cannot see. An agent that actually
plays the game surfaces the journey a new player lives: where it gets lost,
what kills it, when it gets bored. tbaMUD (CircleMUD) is the proving ground
before the agent faces a private game world.

## Getting started

1. **Run the MUD server** (Docker required):

   ```bash
   cd week0_explore/infrastructure
   docker compose up -d
   ```

   The game is then live on `telnet localhost 4000`.

2. **Configure**: settings and secrets live in [`.boukensha/`](.boukensha/).
   Copy `.boukensha/.env.example` to `.boukensha/.env` and fill in your keys.

3. **Run the agent** (current step) from [`week1_baseline/`](week1_baseline/):

   ```bash
   bin/00_config
   ```

## Repository structure

- [`week0_explore/`](week0_explore/) — MUD infrastructure, world exploration,
  the architecture experiments, the play-mud skill, and a realtime viewer for
  watching the agent play ([`visualizer/`](week0_explore/visualizer/))
- [`week1_baseline/`](week1_baseline/README.md) — the baseline agent
  (**boukensha**), built step by step
- `week2_capable/` — the capable agent, built on the baseline (upcoming)
- [`docs/`](docs/) — plans, technical documentation, and the weekly journal

## Documentation

The pre-week experiments set the direction: everything moved from the model
into code became dependable even on a small model, so the agent runs on a
custom agentic loop rather than a coding harness.

- [Week 1 architecture](docs/plans/week1_baseline/architecture.md) — the
  system being built, its components, and the build path
- [Architecture exploration](docs/explore_architectures.md) — the pre-week
  experiments and their conclusions
- [Technical journal](docs/journal/) — one entry per week of the bootcamp
- [Plans](docs/plans/) — the working plans each build executes from

## Status

Pre-week complete: architectures explored, direction chosen. Week 1 in
progress: building the baseline agent, step by step, in
[`week1_baseline/`](week1_baseline/README.md).
