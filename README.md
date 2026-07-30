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

3. **Install the Week 2 gateway** as an isolated editable tool:

   ```bash
   uv tool install --editable ./week2_capable/gateway
   ```

4. **Run the current agent**:

   ```bash
   week2_capable/bin/agent
   week2_capable/bin/agent --player-profile tester
   ```

   Every launch creates an isolated player session under
   `.boukensha/profiles/<player>/sessions/<session>/` and projects cumulative
   evidence into that player's `.boukensha/profiles/<player>/knowledge.db`.

   A benchmark or script can use the same launcher and verify a clean baseline
   before the first model call:

   ```bash
   printf '%s\n' 'Find the bakery and read the menu.' | \
     week2_capable/bin/agent --task-stdin \
     --reset-baseline level1-temple@1 --player-profile tester
   ```

## Repository structure

- [`week0_explore/`](week0_explore/): MUD infrastructure, world exploration,
  the architecture experiments, the play-mud skill, and a realtime viewer for
  watching the agent play ([`visualizer/`](week0_explore/visualizer/))
- [`week1_baseline/`](week1_baseline/README.md): the baseline agent
  (**boukensha**), built step by step
- `week2_capable/`: the Week 2 agent, gateway, viewer, and observability work
- [`docs/`](docs/): plans, technical documentation, and the weekly journal

## Documentation

The pre-week experiments set the direction: everything moved from the model
into code became dependable even on a small model, so the agent runs on a
custom agentic loop rather than a coding harness.

- [Week 1 architecture](docs/plans/week1_baseline/architecture.md): the
  system being built, its components, and the build path
- [Architecture exploration](docs/explore_architectures.md): the pre-week
  experiments and their conclusions
- [Technical journal](docs/journal/): one entry per week of the bootcamp
- [Plans](docs/plans/): the working plans each build executes from

## Status

Week 1 is complete. Week 2 is building the observable agent and its
instrumented gateway in [`week2_capable/`](week2_capable/).
