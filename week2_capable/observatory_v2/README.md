# Boukensha Observatory v2

## What it is

Observatory v2 is the current Observatory frontend. It rebuilds the product
surface on the retained Observatory Python data layer, typed evidence
contracts, and read API. The local supervisor API adds typed start and stop
actions without changing the evidence boundary.

```mermaid
flowchart LR
    R["Retained evidence API"] --> W["Observatory v2 web"]
    S["Local supervisor API"] --> W
    W --> L["Launcher"]
    W --> V["Live"]
    V --> M["Learned-world map"]
    V --> E["Live evidence rail"]
    V --> T["Causal timeline"]
    V --> C["Agent guidance"]
    M --> I["Room inspector"]
```

Detailed behavior and acceptance contracts live in the
[Observatory plans](../../docs/plans/week2_observ/observatory/).

## Layout

```text
observatory_v2/
├── api/
│   ├── observatory_v2_api/
│   │   └── server.py
│   ├── tests/
│   ├── pyproject.toml
│   └── uv.lock
├── web/
│   ├── src/
│   │   ├── live/
│   │   ├── App.tsx
│   │   ├── Launcher.tsx
│   │   └── contracts.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
└── README.md
```

- `api/` owns the loopback-only session supervisor used by launcher and
  lifecycle controls.
- `web/` owns the React application, strict TypeScript contracts, theme,
  launcher, Live shell, map, room inspector, and component tests.
- [`../observatory/`](../observatory/) remains the typed evidence API and
  static application host.

## Install

From `week2_capable/observatory_v2`:

```bash
uv sync --project ../observatory --extra dev
uv sync --project api
cd web
npm ci
npm run build
```

Python and JavaScript dependencies are pinned. Virtual environments,
`node_modules`, and frontend build output remain uncommitted.

## Launch

Build the frontend, then run the supervisor and retained Observatory host in
separate terminals from the repository root:

```bash
cd week2_capable/observatory_v2/web
npm run build
```

```bash
uv run --project week2_capable/observatory_v2/api \
  python -m observatory_v2_api.server
```

```bash
OBSERVATORY_WEB_DIST="$PWD/week2_capable/observatory_v2/web/dist" \
  ./week2_capable/bin/observatory
```

Open <http://127.0.0.1:8787>. The launcher is served at `/`. A Live deep link
uses `/live?player=<player>&session=<session>`.

For frontend development, keep both Python processes running and start Vite:

```bash
cd week2_capable/observatory_v2/web
npm run dev
```

Open <http://127.0.0.1:8791>. Vite proxies evidence requests to port `8787`
and lifecycle requests to port `8792`.

## Configure

Durable non-secret source policy lives in `.boukensha/settings.yaml`. These
environment variables affect the v2 launch directly:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BOUKENSHA_DIR` | repository `.boukensha` | Player profiles, registered sessions, and supervisor state |
| `OBSERVATORY_WEB_DIST` | retained frontend build | Selects the v2 production build for the static host |

The retained API accepts additional evidence-source settings documented in
the [Observatory README](../observatory/README.md#configure). Missing sources
remain visibly unavailable. Neither API invents replacement evidence.

## Screens

### Launcher

The launcher lists registered players and sessions, starts a supervised run,
and opens an existing live session. Session state and available actions come
from typed runtime contracts.

### Live shell

The Live shell keeps player, lifecycle state, and session identity in one
context control. It provides theme, scoped Ask, valid lifecycle actions, and
navigation without changing the selected evidence source. The objective strip,
evidence rail, active-combat panel, and thought age expose retained state
without claiming that a stale observation is current. Message agent inserts
guidance at the next iteration boundary for a running, controllable session.
The rail keeps navigation progress in one stable block, emphasizes retained
friction rules when they fire, and states lifecycle or capture conditions when
measurements would be unsafe. The causal timeline keeps a current snapshot
beside any selected historical prefix, so room and level-up landmarks can step
backward and forward without losing the route back to live. Its cost curve
comes only from retained response economics.

### Learned-world map

The map renders the agent's retained room, traversal, frontier, visit, mob,
object, and thought evidence inside the final Live map pane. Grow, Focus, and
Lantern change presentation without changing learned coordinates. Follow,
Manual, Fit, drag, and zoom operate against the map viewport while the thought
dock and legend remain overlays.

### Room inspector

Selecting a room opens its retained description, exits, visits, sightings,
cost, confidence, and provenance. Agent observations remain distinct from the
separately labelled Atlas reference, and the selected room is restorable from
the `room` URL parameter.

## Verify

From `week2_capable/observatory_v2/web`:

```bash
npm test
npm run build
```

The frontend suite contains 140 tests across 19 files. `npm run build` runs
strict TypeScript checking with `tsc --noEmit` before producing the Vite
production bundle.

The supervisor boundary has a separate Python suite:

```bash
uv run --project ../api --with pytest==9.1.1 pytest ../api/tests
```

## Dependencies

- React and React DOM provide the component application.
- Lucide React provides accessible interface icons.
- Vite builds and serves the frontend.
- TypeScript checks the public frontend contracts in strict mode.
- Vitest, jsdom, and React Testing Library verify behavior and routing.
- The supervisor API uses the Python standard library and has no runtime
  package dependencies.
