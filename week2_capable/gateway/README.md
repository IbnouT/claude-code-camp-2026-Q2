# MUD gateway

The gateway is the instrumented Python interface between Boukensha and the
game. It provides transport, login, wire capture, and a durable event journal.

```mermaid
flowchart LR
    G["tbaMUD"] <-- telnet --> W["wire transport"]
    W --> S["logged-in session"]
    W --> J[("SQLite event journal")]
    J --> X["JSONL projection"]
```

## Layout

The project and its Python package use different names to keep their roles
clear.

```text
gateway/
├── mud_gateway/
│   ├── wire.py
│   ├── session.py
│   └── journal.py
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
