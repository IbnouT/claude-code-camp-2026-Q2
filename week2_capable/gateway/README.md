# MUD gateway

The gateway is the instrumented Python interface between Boukensha and the
game. It provides transport, login, wire capture, structured observations, and
a durable event journal.

```mermaid
flowchart LR
    G["tbaMUD"] <-- telnet --> W["wire transport"]
    W --> S["logged-in session"]
    W --> J[("SQLite event journal")]
    S --> O["rules-first parser"]
    O --> T["conservative position tracker"]
    O --> J
    T --> J
    J --> V["ASGI live SSE + replay"]
    J --> X["JSONL projection"]
    A["Boukensha"] -- MCP stdio --> P["session profile"]
    P --> M["generated command surface"]
    M --> S
    B["benchmark harness"] -- local socket --> R["separate admin process"]
    R --> G
```

## Layout

The project and its Python package use different names to keep their roles
clear.

```text
gateway/
├── admin_process/
│   ├── reset.py
│   └── server.py
├── mud_gateway/
│   ├── admin.py
│   ├── wire.py
│   ├── session.py
│   ├── journal.py
│   ├── commands.py
│   ├── observe.py
│   ├── observation_pipeline.py
│   ├── position.py
│   ├── stream.py
│   ├── api.py
│   ├── profiles.py
│   ├── raw.py
│   ├── results.py
│   └── mcp_server.py
├── scripts/
│   └── live_smoke.py
├── tests/
├── pyproject.toml
└── uv.lock
```

`mud_gateway` is the import namespace. The outer `gateway` directory is the
application project.

## Behavior

- The transport preserves arbitrary socket chunk boundaries.
- Telnet negotiation bytes are filtered from game text and answered safely.
- Login follows name, password, MOTD, menu choice, then the vitals prompt.
- The password is replaced with a length-preserving redacted event before
  anything is persisted.
- SQLite runs in WAL mode with one journal writer.
- Events commit before subscribers receive them.
- Unknown journal schema versions are refused.
- JSONL export provides a supported projection for file-based consumers.
- One typed registry generates command validation and every MCP projection.
- A deny-by-default profile fixes the advertised tools for the whole session.
- Direct and grouped surfaces are generated from the same capabilities.
- Disabled capabilities are rejected by the server as typed errors.
- Profile identity, capability digest, coverage, and schema bytes are recorded.
- Named profiles deny `send_raw`. An explicit allowlist can enable it, and
  every use records a capability-gap event with its reason.
- Immortal credentials and typed admin operations stay outside this process.
- A separate local-socket process owns typed immortal operations and reset.
- Reset restores the benchmark character, then verifies through mortal
  `score` and `look` output.
- Two identical resets must produce identical fully read mortal state.
- Live SSE and historical replay use one deterministic event serializer.
- `Last-Event-ID` resumes from the durable journal sequence.
- Slow subscribers are dropped and recorded rather than blocking the game.
- Canonical wire replay reconstructs exact captured bytes, including
  length-preserving zeroes for credentials redacted before persistence.
- ANSI colour and line shape produce typed room, exit, vital, and state
  observations.
- Every observation records confidence, method, parser version, and its source
  wire range.
- Unknown lines remain `unparsed` events and contribute to the parse-miss rate.
- Position uses arrival paths, exits, and neighbourhoods. A duplicate title is
  never sufficient evidence to merge two places.
- The agent-facing `observe` and `navigate` capabilities remain disabled.

## Verification

Run the hermetic suite:

```bash
uv sync --extra dev
uv run pytest
```

Run the live smoke test against the local game:

```bash
MUD_PASSWORD='...' uv run python scripts/live_smoke.py --player poucet
```

The live smoke test logs in, runs `look`, `score`, and `exits`, reconstructs inbound
traffic from the journal, and checks that no credential reached persisted
evidence.

Measure the named candidate profiles:

```bash
uv run python -m mud_gateway.mcp_server --measure
```

Replay every retained session and report parser coverage:

```bash
uv run python scripts/replay_observations.py
```

Prove one configured surface:

```bash
uv run python -m mud_gateway.mcp_server --prove
uv run python -m mud_gateway.mcp_server \
  --profile direct-full --allow look,move,send_raw --prove
```

Run the repeatable live reset gate:

```bash
MUD_ADMIN_PASSWORD='...' uv run python scripts/reset_smoke.py \
  --db /tmp/gateway-reset-smoke.db
```

Serve live and replay views locally:

```bash
uv run python -m mud_gateway.api \
  --journal ../../.boukensha/gateway/gateway.db
```

Verify a retained journal replays deterministically:

```bash
uv run python scripts/stream_smoke.py \
  --journal ../../.boukensha/gateway/live-smoke.db
```
