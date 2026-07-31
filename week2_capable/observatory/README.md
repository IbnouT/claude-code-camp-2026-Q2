# Boukensha observatory

The observatory is a local flight recorder and experiment studio for the
agent. Its evidence plane is read-only. A narrow authenticated control plane
can direct one selected live agent. Every historical prefix is reconstructed
through the same deterministic projector.

```mermaid
flowchart LR
    R["Launcher registry"] --> A["Starlette evidence API"]
    G["Gateway replay and SSE"] --> A
    E["Agent events"] --> A
    B["Recorded experiment samples"] --> A
    K["Per-player knowledge stores"] --> A
    A --> D["One deterministic projector"]
    D --> W["Selected evidence prefix"]
    W --> L["Live and Sessions"]
    L --> C["Authenticated agent boundary"]
```

## Current interface

Live is connected to registered runtime evidence:

- Four destinations: Live, Sessions, Experiments, and Knowledge.
- One context-aware header with player, applicable session, Load, and theme.
- Persistent dark and light themes.
- Comfortable and dense design tokens.
- Registered players and sessions discovered without scanning by file time.
- Live SSE and recorded replay pass through one deterministic event reducer.
- World, objective, cost, tokens, iterations, activity, and source completeness.
- One causal clock reconstructs every panel at a selected sequence.
- Pause, scrub, bookmark, and return-to-live controls.
- Grow, Focus, and Lantern world modes.
- One evidence-backed world surface shared by Live and Sessions.
- Reset, relocation, and reconnect receipts break learned traversal continuity.
- Duplicate room identities, candidate explanations, sightings, and objective beacons.
- An isolated observer atlas with overview and zone level-of-detail.
- A structured list equivalent for both the journey graph and atlas canvas.
- Scoped Ask entry inside the active workspace.
- Authenticated guidance, goal revision, pause, resume, and stop in Live.
- Wire, Parsed, Rendered, Believed, and Truth remain distinct evidence forms.
- Truth and unavailable sources remain visibly missing or incomplete.
- Player switching replaces every session-bound evidence projection.
- Desktop and narrow layouts retain the same information and actions.
- Each primary workspace loads as its own bounded JavaScript and CSS chunk.
- Keyboard focus returns to the invoking control after dialogs close.
- Forced colors, reduced motion, and 200 percent layout remain operable.

Sessions turns an explicitly selected experiment sample into an investigation:

- Agent, gateway, Telnet wire, parsed state, and verified outcome stay distinct.
- Story, sequence, evidence, cost, and diagnostic lenses share one selection.
- Event, turn, and milestone replay expose only the selected evidence prefix.
- Every retained record opens exact sanitized fields, ancestry, and correlations.
- Structured filters and saved views narrow evidence without hiding its source.
- Wire, Parsed, Rendered, Believed, and Truth expose missing forms as gaps.
- Ten deterministic diagnostics show rules, thresholds, alternatives, and evidence.
- Cache-aware per-response costs reconcile to the retained attempt cost curve.
- Raw response cost fields remain visible beside the reconciled ledger.
- Ask uses local typed operations, the selected run, and the replay moment.
- Benchmark outcome enters only through the selected experiment-sample link.
- Stable URLs restore the player, run, lens, room, and selected record.

Experiments turns retained cohorts into a controlled comparison:

- The objective, independent predicate, starting state, and reset identity are explicit.
- Typed controls come from the model, gateway, agent, and policy registries.
- Raw, minimal, and full J1 arms explain their only controlled difference.
- Six stop criteria and maximum spend are visible before confirmation.
- Validation rejects unknown fields, reset gaps, and inconsistent spend math.
- One-variable forks retain their parent and exact changed feature.
- Sample identities and queue order remain stable across stop and resume.
- Persisted jobs reopen from the experiment library with their definition, state, spend, and collected cohort.
- Setup failures, exclusions, agent failures, and successes stay distinct.
- Aggregates open their contributing samples through standard Sessions routes.
- First divergence aligns representative runs by semantic action.
- Cost, token classes, payload size, and movement share expose attention economics.
- Rendering and parser counterfactuals are labelled as non-causal replay.
- Paid execution is disabled by default and requires local policy, validation, and explicit confirmation.
- Confirmed jobs persist stable sample identities, stop and resume safely, and expose retained samples through Sessions.
- An unconfirmed request is rejected before execution policy is evaluated.

Knowledge makes one player's cumulative memory inspectable:

- Overview, Map, Entities, Progression, Snapshots, and History share one player.
- Learned state, observer truth, and their Diff remain separate layers.
- Dense maps aggregate by zone before rendering at most 120 room identities.
- Entities preserve distinct identities and mobile or respawning sightings.
- Progression groups vitals, equipment, conditions, milestones, and objectives.
- Every assertion opens its history, contradictions, confidence, and supports.
- Every support exposes its gateway session, sequence, parser, method, and wire digest.
- Source pivots open Sessions only when the exact gateway correlation is retained.
- Snapshot digests are verified before a restore action becomes available.
- Reset and restore require the selected authenticated live session and exact sequence.
- Recovery appends history and never asks the browser for a player password.

Incidents preserve a reviewable moment without flattening the investigation:

- Notes and bookmarks attach to stable evidence identities across replay movement.
- Export renews redaction and seals the selected chronological prefix.
- Prefix projection excludes future records, world state, truth, diagnostics, and cost.
- Capsules include player-scoped knowledge, diagnostic history, source versions, and gaps.
- Integrity is verified before the standard Sessions workspace opens the capsule.
- Offline mode stops runtime polling and offers no control, Ask, provider, or MUD action.
- Diagnostic prevalence links back to its contributing recorded sessions.

The browser tests use deterministic representative evidence. The launched
product reads the local runtime registry and selected session journals.
Sessions and Experiments read explicitly correlated benchmark evidence.
Knowledge reads each selected player's owned `profiles/<player>/knowledge.db`
through the gateway's read-only `KnowledgeStore` contract.

### Reset boundary

The product surface is new. Proven infrastructure remains:

| Classification | Content |
| --- | --- |
| Retained | Typed read API, evidence contracts, capability transport, build setup, pinned dependencies, and test harness |
| New | App entry, product shell, destination hierarchy, tokens, styles, responsive behavior, and accessible primitives |
| Adapted | Capability state consumed by contextual workspace status |
| Obsolete | Earlier presentation components not imported by the new entry |

## Layout

```text
observatory/
├── observatory_api/
│   ├── app.py
│   ├── capabilities.py
│   ├── contracts.py
│   ├── incidents.py
│   ├── settings.py
│   ├── projections/
│   └── sources/
├── tests/
├── web/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── data/
│   ├── package.json
│   └── vite.config.ts
├── pyproject.toml
└── README.md
```

## Install

From `week2_capable/observatory`:

```bash
uv sync --extra dev
cd web
npm install
npx playwright install chromium
npm run build
```

The Python and JavaScript dependencies are pinned. Frontend build output and
package directories remain uncommitted.

Playwright provides reproducible browser workflows. Axe runs semantic
accessibility checks inside the same Chromium matrix.

## Launch

From the repository root:

```bash
./week2_capable/bin/observatory
```

Open <http://127.0.0.1:8787>. The launcher binds to loopback by default.

For frontend development, run both processes:

```bash
./week2_capable/bin/observatory
cd week2_capable/observatory/web
npm run dev
```

Open <http://127.0.0.1:5174>. Vite proxies `/api` to the local read API.

## Configure

Durable non-secret policy lives in `.boukensha/settings.yaml`. Environment
variables provide process-local source paths and overrides:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BOUKENSHA_DIR` | nearest `.boukensha` ancestor | Registered player sessions and runtime evidence |
| `BOUKENSHA_WORLD` | `observatory.world.path` | One-run override for the observer atlas source |
| `OBSERVATORY_ENABLE_SECTOR_OVERRIDES` | `0` | Expose the reviewed semantic atlas categories when set to `1` |
| `OBSERVATORY_GATEWAY_URL` | `http://127.0.0.1:8765` | Gateway HTTP and SSE source |
| `OBSERVATORY_AGENT_EVENTS` | disabled | Agent event source |
| `OBSERVATORY_BENCHMARK_ROOT` | disabled | Benchmark evidence root |
| `OBSERVATORY_EXPERIMENT_EXECUTION` | `observatory.experiments.execution_enabled` | One-run execution-policy override |
| `OBSERVATORY_EXPERIMENT_MAX_SPEND_CAP` | `observatory.experiments.max_spend_cap_usd` | One-run hard local spend ceiling |
| `OBSERVATORY_EXPERIMENT_STATE_ROOT` | `observatory.experiments.state_path` | Untracked definitions, jobs, and receipts |
| `OBSERVATORY_WEB_DIST` | `web/dist` | Built frontend location |
| `OBSERVATORY_COPILOT_MODEL` | disabled | Optional Anthropic translator model |
| `OBSERVATORY_COPILOT_ENDPOINT` | Anthropic messages API | Translator REST endpoint |
| `OBSERVATORY_COPILOT_SPEND_CAP` | `0` | Process-local translator cost ceiling |
| `OBSERVATORY_COPILOT_INPUT_RATE` | `0` | Input dollars per million tokens |
| `OBSERVATORY_COPILOT_OUTPUT_RATE` | `0` | Output dollars per million tokens |
| `OBSERVATORY_REVISION` | launcher revision | Repository revision recorded in capsules |
| `OBSERVATORY_DISABLED_FEATURES` | empty | Comma-separated features hidden by policy |

Unavailable or disabled sources remain visible with an explanation. The
observatory never invents data to fill an absent source.

The atlas parser retains room numbers, titles, zones, and exits. Atlas truth is
quarantined from agent belief. A live or recorded room is not correlated to an
atlas room unless its evidence includes the stable world room number.
The atlas transport accepts a reviewed semantic-sector correction file. Loading
verifies each correction against the original sector before exposing the
corrected category. Without the verified file and explicit enablement, the API
returns raw atlas sectors. The configured `.wld` files remain unchanged.

The durable atlas path belongs in `.boukensha/settings.yaml`:

```yaml
observatory:
  world:
    path: week0_explore/circlemud-world-parser/assets/wld
```

Benchmark evidence and experiment policy are also durable non-secret settings:

```yaml
observatory:
  benchmark:
    path: .boukensha/benchmarks
  experiments:
    execution_enabled: false
    max_spend_cap_usd: 10.00
    state_path: .boukensha/experiments
```

Enabling policy does not confirm a run. Validation returns the effective
configuration, reset identity, deterministic queue, and maximum spend. A
separate request must explicitly confirm that spend before a runner can start.

Optional model translation uses durable non-secret policy:

```yaml
observatory:
  disabled_features: [
    # copilot-model,
    # benchmark-execution
  ]
  copilot:
    model: claude-haiku-4-5
    endpoint: https://api.anthropic.com/v1/messages
    spend_cap_usd: 0.25
    input_rate_per_million: 1.00
    output_rate_per_million: 5.00
```

`ANTHROPIC_API_KEY` is the only copilot value in `.boukensha/.env`.
Translation becomes available only when the key, pinned model, rates, and
positive spend cap are all present. It receives redacted question text, not
evidence. It can select only an allowlisted operation, which is then checked
against the active player, space, session or run, and replay prefix.

The local deterministic planner always runs first. A user must opt into model
translation for each unmatched question. Model tokens and cost are reported
separately from agent and experiment spend.

Relative source paths are resolved from the repository root by the launcher.
For the local benchmark evidence:

```bash
OBSERVATORY_BENCHMARK_ROOT=.boukensha/benchmarks \
  ./week2_capable/bin/observatory
```

The active destination is encoded as `?space=<name>`. Player and session remain
explicit shell context.

### Live control boundary

Live control does not send game commands from the browser. The launcher gives
each agent process an authenticated local operator endpoint:

```mermaid
sequenceDiagram
    participant U as Operator
    participant O as Observatory
    participant A as Selected agent
    U->>O: Confirm guide, revise, pause, resume, or stop
    O->>O: Verify live session and expected sequence
    O->>A: Authenticated session-scoped request
    A-->>O: Idempotent receipt
    A->>A: Apply at next safe iteration boundary
    A-->>O: Project state and append evidence
```

- The browser sends no credential.
- The API reads the selected session token server-side.
- Player, session, endpoint, and expected sequence must all match.
- Guidance and revisions enter context as labelled operator messages.
- Pause and stop cannot interrupt a provider request already in flight.
- A stale, ended, mismatched, or unavailable target is rejected.
- Operator state and applied directives become observable evidence.

Incident export is available only for an explicitly correlated recorded
session. The loaded capsule remains visibly offline and read-only.

## Verify

```bash
uv run pytest
uv lock --check
cd web
npm test
npm run build
npm run test:budget
npm run test:e2e
```

UI changes require rendered checks at desktop and narrow widths.

- Live gates time travel, return to combat, player isolation, and control.
- Sessions gates replay, exact source reachability, Ask scope, and cost.
- Knowledge gates player isolation, provenance, recovery, and dense rendering.
- Incidents gate renewed redaction, integrity, exact prefixes, and offline reopen.
- Shared gates cover focus, source failure, themes, accessibility, and overflow.

## Product hardening

The production surface keeps these gates executable from a fresh clone:

| Gate | Enforced behavior |
| --- | --- |
| Unit | Components, preferences, capability contracts, redaction, and imports |
| End to end | Desktop and 390-pixel flows in Chromium |
| Accessibility | Automated semantic audit, forced colors, and reduced motion |
| Failure | Unavailable and disabled sources remain explicit |
| Policy | Named capabilities disappear from discovery and navigation |
| Performance | JavaScript under 300 KB raw and 90 KB gzip |
| Performance | CSS under 60 KB raw and 12 KB gzip |

The architecture and feature acceptance contracts live in
`docs/plans/week2_observ/observatory.md` and `product_spec.md`.
