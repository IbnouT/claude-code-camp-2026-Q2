# Observatory

The observatory is a flight recorder, debugger, and experiment studio for an
agent acting in a persistent world. It should explain not only what happened,
but what the agent believed, what evidence supported that belief, where the
belief diverged from reality, and what the divergence cost.

The reference monitor and the Week 0 visualizer set a useful floor. They do not
set the architecture or product ceiling.

`product_spec.md` defines the feature-level interaction contracts and acceptance
gates. The HTML files in `mockups/` define the visual references.

## Product vision

The observatory should make four difficult questions easy to answer:

- What is happening now?
- Why did the agent make this decision?
- Which system design performs better under a controlled experiment?
- What has this player learned across sessions?

Three cross-cutting capabilities define the product.

### Belief versus reality

The primary diagnostic view compares three distinct layers:

- Agent belief: the state and objective implied by the context and actions.
- Parsed inference: the gateway's typed interpretation, with confidence.
- Observer truth: optional world data and verified outcomes, never fed to the
  agent.

A divergence is a first-class event. False completion, stale position,
duplicate-room ambiguity, and unsupported certainty become visible states
instead of conclusions hidden in a transcript.

The layers must remain visibly and technically separate. Observer truth can
grade and diagnose an agent, but it cannot leak into agent-facing state.

### Evidence-backed time travel

One scrubber controls the whole interface. Selecting any moment reconstructs:

- the room and journey map
- the agent's latest known belief
- parser output and unresolved ambiguity
- active goal and recent decisions
- tool, command, and wire activity
- token, latency, and cost accumulation

Every derived fact links back to its evidence. A room title, exit, health value,
or completion claim can be opened to reveal its confidence, method, parser
version, trace, and exact redacted wire range.

Live mode and replay mode use the same event reducer. Pausing the view never
pauses ingestion. Returning to live catches up without duplicate or missing
events.

### Counterfactual experiment studio

Recorded wire evidence can be replayed through alternative deterministic
components without calling the model or touching the MUD:

- parser version
- model-facing rendering policy
- tool profile
- position resolver
- diagnostic rule set

The studio compares actual and counterfactual projections side by side. It
shows which observations changed, where confidence moved, how many bytes or
tokens the agent would have received, and which conclusions would no longer be
supported.

A model-backed experiment remains a separate paid operation with an explicit
budget and ledger.

```mermaid
flowchart LR
    W["Wire evidence"] --> P["Parser"]
    P --> O["Typed observations"]
    O --> B["Agent belief"]
    O --> J["Journey state"]
    A["Agent decisions"] --> B
    T["Observer truth"] --> D["Divergence engine"]
    B --> D
    J --> D
    D --> UI["Observatory"]
    W --> UI
    O --> UI
    A --> UI
    C["Cost and token evidence"] --> UI
    UI --> R["Counterfactual replay"]
    R --> P2["Alternative projections"]
    P2 --> UI
```

## Design principles

- Evidence before assertion: every conclusion opens to its source.
- No orphan evidence: every captured record, field, and retained value remains
  inspectable in a meaningful form and as its exact sanitized source.
- No dead-end dimension: evidence can move down to source detail, up to its
  containing turn and run, or sideways through every captured causal,
  chronological, spatial, model, tool, gateway, cost, quality, and
  configuration relation.
- Visible capture gaps: a missing peer or correlation is named as unavailable
  evidence. It is never hidden behind an empty panel or inferred into existence.
- Uncertainty stays visible: ambiguity is information, not a rendering defect.
- One causal model: wire, parser, tool, model, cost, and state are correlated by
  stable identifiers.
- Live equals replay: both paths produce the same projection for the same event
  prefix.
- Progressive disclosure: the first screen stays calm, detail is one action
  away.
- Local first: core inspection and deterministic analysis work without cloud
  services.
- Spend last: common analysis is deterministic before an LLM is considered.
- Read-only by default: the observatory cannot issue game commands.
- Configuration is explicit: unavailable data produces an honest capability
  state, not an empty chart.
- Observer truth is quarantined: it cannot enter an agent prompt or tool result.
- Unknown data survives: new event kinds remain searchable and inspectable.

## Experience north star

The product should feel like one instrument with four question-led spaces, not
a collection of dashboards. Map, sequence, evidence, cost, and diagnostics are
coordinated lenses inside each relevant workspace.

The hierarchy is:

1. Live: understand and control the current run.
2. Sessions: replay and explain any recorded moment.
3. Experiments: define, run, and compare controlled variants.
4. Knowledge: inspect what one player has learned across sessions.

Ask and search are scoped tools available in every space. They do not become
separate destinations.

The product has two explicit planes:

- The read plane reconstructs and inspects evidence. It never mutates journals,
  observations, knowledge history, or the game world.
- The control plane launches or stops mortal agent runs and delivers confirmed
  goal revisions through the launcher. It never sends immortal commands or
  converts observer truth into agent input.

The interface succeeds when these workflows feel obvious:

- A diagnostic appears during live play. One click pauses at the triggering
  moment, frames the affected journey segment, and opens supporting evidence.
- A false completion shows the agent's claim beside the unmet objective and the
  last reliable world state.
- Selecting a room paints its visits on the timeline and selecting a turn paints
  its position on the map.
- Comparing two runs jumps first to their first meaningful divergence, not to
  two unrelated transcript timestamps.
- Asking "why did it stop?" returns a concise answer whose cited claims open the
  exact evidence.

### Anti-goals

- No homepage made of unrelated metric cards.
- No raw JSON as the primary reading experience.
- No separate page for every event or log source.
- No chart without a decision or investigation question.
- No permanent three-column squeeze on narrow screens.
- No hidden uncertainty behind a confident icon.
- No decorative animation, 3D world, or game-like chrome.
- No assistant answer without inspectable evidence.
- No feature included only because Week 0 or the reference had it.

## Information architecture

The interface is organized by investigation task, not by storage file. Mode
changes preserve the selected run, time, room, trace, and evidence.

### Live

Live answers "what is happening now?"

- one active player selected from the runtime registry, with fast switching
  between that player's live and recently ended sessions
- live causal activity stream
- current room, full player state, position confidence, goal, and agent status
- journey map with recent path and unresolved location candidates
- cost, context, latency, and token burn
- instrumentation health and connection freshness
- automatic diagnostic cards

Full player state includes gold, prompt vitals, hungry, thirsty, poisoned,
drunk, encumbered, and posture. Unknown and stale values remain visible as
capture states. The status rail and map marker share the same projection.
Abnormal conditions use restrained glyphs. Normal state does not become a row
of decorative badges.

The journey map has three focus modes:

- Focus is the default. At the current scale, it adds complete breadth-first
  shells whose full drawn room footprints stay inside the map pane and outside
  actual overlay rectangles, with an 18-room shell cap. A footprint includes
  the cell, title, and external badges. It then fills learned paths through
  adjacent rooms meeting the same geometry. A bridge crossing a persistent
  overlay remains visible when it is required to preserve an otherwise
  admissible path. The rendered set stays connected to the agent. Explicit
  entry centers the current room without changing scale.
- Grow presents the full learned journey and supports free panning.
- Lantern keeps the full graph faintly present. The current room is fully lit,
  one hop is strong, and two hops remain legible.

Focus remains agent-relative while permitting bounded local inspection. It
never writes camera scale. A drag keeps Focus active and enters Manual at the
exact center and scale where the gesture starts. Agent movement resumes Follow
without changing scale. The current room may move within a central dead zone.
Crossing that boundary moves the camera only by the excess distance with
damped, non-overshooting motion. An unconnected position jump snaps instead of
presenting control movement as traversal. Learned connections crossing the
Focus set render as fixed-size solid chevrons on the pane edge. Their
cross-axis position follows hidden-room geometry and slides along the edge only
to avoid complete room footprints. Frontier evidence remains a dashed room
stub ending in a dot.

Lantern recenters on the current room without changing scale and resumes
Follow. A Lantern drag hands the same framing to Grow and Manual. Grow can also
follow the agent, hold the investigator's manual framing, or fit selected
evidence. Focus room selection tests the actual toolbar, legend, and thought
dock rectangles plus eight pixels instead of reserving full-width bands. The
temporary drag hint is not an occluder and disappears after the first drag in
a session. Fit excludes persistent surfaces' outer edge insets. A room opens a
compact detail popover
with visits, entities, exits, confidence, and provenance. The objective beacon
appears only when a cited sighting or durable knowledge assertion supports a
known target location.

The opening state prioritizes the world and current intent. Secondary measures
stay quiet until they change or cross a meaningful threshold.

### Sessions

Sessions answers "why did this happen in this run?"

- player and session discovery without latest-file inference
- replay, pause, step, scrub, and synchronized spatial and temporal lenses
- an unfoldable session sequence from lifecycle and goal revisions through
  turns, tool calls, gateway commands, wire frames, observations, and state
- trace waterfall from model turn to tool call, command, wire, parse, and state
- belief versus reality comparison
- evidence inspector for raw, parsed, rendered, and believed forms
- goal and completion-claim audit
- parser misses, low-confidence facts, and stale evidence
- loop, stall, retry, and correction analysis

Investigation begins from a selected session, fact, diagnostic, map location,
timeline range, or question. The workspace keeps that subject in focus while
the user moves between causal, spatial, cost, and evidence lenses.

Replay supports automatic playback at human-readable speeds and event, turn,
or milestone stepping. At any paused moment, "Ask why" scopes the query to the
selected evidence prefix and opens every citation in place.

Cost is a Sessions lens, not a separate destination. Totals, curves, token
classes, and efficiency measures are clickable pivots into billed responses,
their prompts, actions, rooms, progress, and source usage records.

### Experiments

Experiments answers "which design performs better, and why?"

- controlled scenario definitions with objective, baseline, success predicate,
  model, tools, rendering, parser, limits, repetitions, and spend cap
- gateway and agent feature controls generated from one versioned runtime
  registry, so a new registered flag appears without a hand-coded form change
- reset verification before every sample
- explicit validate, launch, resume, stop, and compare lifecycle
- two or more runs aligned by semantic milestones
- rendering, parser, model, and tool-profile differences
- success and final-state correctness
- cost, calls, latency, invalid calls, and corrections
- observation and belief divergence
- path efficiency and information gained

Alignment uses room transitions, tool calls, objective milestones, and verified
state changes. Wall-clock alignment is available, but it is not the default.
Every experiment and sample links to its full Sessions evidence.

The workbench separates aggregate and per-run results. Repetitions show
distribution, outliers, setup failures, and excluded samples. One sample may be
watched live at a time while the remaining queue stays controlled. Stop
criteria include success, verified predicate, iteration, time, spend, and
operator stop.

Every repetition resets the selected player and knowledge to the same versioned
baseline, then verifies the resulting digest before a model call. A mismatch
blocks the sample and explains the field that drifted. Forking an experiment
shows the exact variables that changed.

### Knowledge

Knowledge answers "what does this player know, and why?"

- learned world with zone, cluster, and room levels of detail
- frontier, revisits, entities, objects, and mobile sightings
- full player state, progression, inventory, and milestones
- per-fact provenance, confidence, parser version, and contradictions
- snapshots, recoverable reset, and restore
- belief and observer-truth overlays that remain technically separate

Knowledge is cumulative per player. A selected fact opens every supporting
session and observation without flattening mobile entities or duplicate rooms.

Learned, Truth, and Diff are explicit layers. Truth remains quarantined from
agent-facing data. Knowledge reset always snapshots first. Restore appends a
new revision instead of rewriting history.

The learned world adapts to scale:

- room detail for a small neighbourhood
- clusters for dense learned regions
- zones for the complete known world

Entities support search, filters, type grouping, pagination, mobile sighting
history, and multiple simultaneous instances. The same information remains
usable on a narrow screen and with several Observatory instances reading the
store concurrently.

### Ask and search

Ask is a grounded investigation copilot embedded in every mode. It answers
natural-language questions about the evidence without becoming a second source
of truth. Structured search uses the same entry point and remains fully usable
when model access is disabled.

Example questions:

- Why did the agent believe the journey was complete?
- Where did position confidence first fall below 0.7?
- Which rooms consumed the most model cost without producing progress?
- Compare raw and full rendering after the third room transition.
- Show every claim supported only by a low-confidence parser result.
- What changed between these two runs before their paths diverged?

Each answer includes:

- a visible query plan
- cited events, traces, wire references, rooms, and runs
- confidence and missing-data notices
- links that open the relevant timeline range and panels
- token and cost accounting when a model is used

The copilot has three execution tiers:

1. Saved questions and local aggregations answer common requests with no model.
2. A deterministic query builder maps supported phrases and filters to a typed
   observatory query.
3. An optional model translates open-ended language into the same typed query
   and summarizes returned evidence.

The model never receives database access or executes arbitrary code. It emits a
query abstract syntax tree that is schema-validated, permission-checked, and
shown before execution when the request is broad or costly. Summaries may only
cite returned evidence. Unsupported claims are labeled as hypotheses.

Model use is opt-in per installation and per request. Redaction, maximum input
size, allowed evidence fields, model, and spend cap are configurable. The model
backend uses the repository's direct REST convention, without a vendor SDK or
agent framework.

## Experience design

The visual character should feel like a purpose-built instrument, not an admin
template. It should be quiet at rest and precise under pressure.

### Investigation workspace

The default desktop layout has four coordinated regions:

```text
┌ Session, mode, clock, data health, profile, search ───────────────────────┐
│                                                                         │
│  World and belief canvas        │  Current state and diagnostic stack   │
│                                 │                                       │
├ Causal timeline and cost curve ─┴───────────────────────────────────────┤
│ Evidence drawer: raw | parsed | rendered | believed | observer truth    │
└ Command palette, keyboard help, live/replay status ──────────────────────┘
```

Any panel can focus, dock, or collapse. A selected event, trace, room, or time
range is reflected across every panel and encoded in the URL.

The narrow layout becomes a focused sequence rather than a squeezed dashboard:

1. status and active diagnostic
2. map or timeline
3. evidence and details

### Visual grammar

- One canonical header carries player, session, space, clock, source health,
  theme, search, and control status. Feature work does not introduce competing
  shells.
- Design tokens define color, typography, spacing, elevation, borders, motion,
  density, and graph semantics. Shared components consume those tokens.
- State uses a restrained neutral foundation with semantic accents.
- Confidence uses text, shape, border treatment, and pattern, not color alone.
- Actual, inferred, believed, and counterfactual data have stable visual forms.
- Cost overlays never obscure causal ordering.
- Motion communicates transition only and respects reduced-motion settings.
- Dense and comfortable display modes support different investigation styles.
- Typography distinguishes prose, evidence, identifiers, and numeric measures.
- Empty, stale, unavailable, reconnecting, and incomplete are distinct states.

Dark is the default operator theme. A first-class light theme supports daylight
use and print, with a persistent toggle and equivalent contrast, hierarchy, and
semantic meaning. Terminal and raw-evidence surfaces remain dark in both themes
to preserve ANSI and monospace legibility.

### Interaction model

- Space pauses and resumes the visual clock.
- Left and right step by causal event.
- Shift plus left or right steps by model turn.
- `/` opens global evidence search.
- `Cmd/Ctrl+K` opens the command palette.
- `E` opens provenance for the selected fact.
- `B` bookmarks an incident moment.
- `C` starts a comparison from the current selection.
- `?` opens contextual help.

Keyboard and pointer operations have equivalent outcomes. Focus remains visible
and is restored when drawers close.

## Diagnostic intelligence

Diagnostics are deterministic detectors with evidence, severity, and a
resolution state. They never silently rewrite the session.

Initial detectors include:

- False completion: the agent stops without objective evidence.
- Belief divergence: agent belief conflicts with parsed or verified state.
- Position ambiguity: multiple room candidates remain unresolved.
- Confusion loop: a path or action sequence repeats without new information.
- Progress stall: cost grows without objective, map, or state progress.
- Parse degradation: misses or low-confidence observations spike.
- Corrective-call cluster: invalid or ineffective calls trigger retries.
- Stale action: a decision relies on evidence older than a configured horizon.
- Context churn: repeated context contributes cost without changing action.
- Instrumentation gap: sequence, trace, source, or clock evidence is incomplete.

Each diagnostic card answers:

- What was detected?
- Why does it matter?
- Which evidence triggered it?
- What alternative explanations remain?
- What should an investigator inspect next?

Rules are versioned and replayable. Thresholds are configurable. The UI exposes
why a rule fired instead of presenting an unexplained score.

## Causal and evidence model

The gateway event envelope remains the session evidence contract:

- `seq`
- `session`
- `at`
- `kind`
- `trace_id`
- `data`

The observatory builds immutable projections from this stream. It does not
replace the gateway journal.

### Causal graph

Known event relations form a typed graph:

```mermaid
flowchart LR
    M["Model turn"] --> TC["Tool call"]
    TC --> C["MUD command"]
    C --> WF["Wire frame"]
    WF --> PO["Parsed observation"]
    PO --> PS["Position state"]
    PO --> MR["Model rendering"]
    MR --> M2["Next model turn"]
    TC --> TR["Tool result"]
    K["Token, latency, cost"] --> M
    G["Goal and stop claim"] --> M
```

`trace_id` is the principal cross-layer correlation key. Event sequence remains
the authoritative session order. Additional parent and link fields may enrich
the graph without changing the envelope.

The vocabulary should follow OpenTelemetry concepts where they fit, especially
trace, span, event, resource, links, and attributes. Domain events remain
domain-specific rather than being forced into generic telemetry.

### Evidence lens

The lens presents one fact through five possible forms:

| Form | Purpose |
| --- | --- |
| Wire | Redacted bytes or text received from the MUD |
| Parsed | Structured observation and parser metadata |
| Rendered | Exact model-facing representation |
| Believed | State inferred from subsequent agent behavior |
| Truth | Optional observer-only world or verified outcome |

Missing forms remain visibly absent. The interface never synthesizes a value to
fill a gap.

### Attention economics

Cost is connected to progress rather than displayed only as a total:

- cost and tokens per verified state change
- cost per new room or resolved ambiguity
- cost per successful action
- cost spent in loops and corrections
- context bytes or tokens repeated without decision impact
- information gain per turn
- cached and uncached input separately
- marginal cost after the last objective milestone

These measures make preprocessing and rendering experiments testable. A smaller
payload is not called cheaper unless total journey evidence confirms it.

## World and journey visualization

The map has three semantic zoom levels.

### Journey

A compact graph shows the current run, recent trail, frontier, loops, hazards,
and unresolved candidate positions. This level favors clarity over geographic
completeness.

### Neighbourhood and zone

The current candidate set expands into nearby known rooms and exits. Differences
between belief, inference, and truth are overlaid without collapsing duplicate
titles.

### Atlas

The optional CircleMUD world source enables zone and world exploration. A full
atlas may contain more than twelve thousand rooms, so it must use a measured
Canvas or WebGL renderer and level-of-detail aggregation. It must not create one
DOM node per room.

The Week 0 visualizer contributes useful interaction and adapter ideas:

- current-room emphasis
- recent trail and frontier
- room graph and directional exits
- hazards, deaths, darkness, and unknown position
- compact cockpit information

It does not contribute its demo data adapters, committed build output, terminal
emulation, voice behavior, or assumption of one consolidated state object.

The CircleMUD parser may provide observer-only rooms, exits, zones, doors,
mobiles, objects, and shops. Its data is visually marked as truth-layer data and
is isolated from all agent-facing paths.

## Run comparison

Comparison is a first-class workspace, not a collection of charts.

The alignment engine identifies:

- common starting evidence
- shared room or state milestones
- first behavioral divergence
- converged or divergent outcomes
- unmatched segments

The comparison view includes:

- synchronized journey maps
- stacked causal timelines
- belief and position confidence
- rendered observation differences
- tool and command distributions
- cumulative and marginal cost
- latency and corrective calls
- diagnostics unique to each run

An investigator can pin a divergence and ask the copilot to explain the evidence
available to each run at that moment.

## Search and investigation language

Structured search remains available without the copilot.

Examples:

```text
kind:parse_miss
confidence:<0.70
trace:77aea1e50d7540f8
room:"The Entrance To The Newbie Zone"
diagnostic:false_completion
cost:>0.01 after:milestone("entered newbie zone")
run:a differs:run:b field:position
```

The query language produces stable URLs and saved views. Autocomplete is driven
by the event schema and detected data-source capabilities.

## Incident capsules

An incident capsule is a portable, sanitized investigation:

- selected event and time range
- relevant causal subgraph
- bookmarks and investigator notes
- parser, profile, model, and rendering versions
- repository revision
- diagnostic results
- redacted evidence references
- optional comparison run

Capsules are local files by default. Export validates redaction again and never
includes credentials. A capsule can reproduce the projection without contacting
the live MUD or model provider.

## Architecture

The observatory separates a read plane from a narrow mortal control plane.

```mermaid
flowchart TB
    G["Gateway HTTP, SSE, replay, wire"] --> B["Observatory read API"]
    AJ["Agent event JSONL"] --> B
    BR["Benchmark reports"] --> B
    KS["Knowledge store, when available"] --> B
    WT["Optional world truth"] --> B
    B --> C["Typed browser client"]
    C --> R["Deterministic event reducer"]
    R --> P["Projection worker"]
    P --> W["Live"]
    P --> S["Sessions"]
    P --> E["Experiments"]
    P --> K["Knowledge"]
    P --> X["Map, evidence, cost lenses"]
    P --> Q["Ask and search"]
    Q --> QE["Validated query engine"]
    QE --> P
    QE -. "optional, budgeted" .-> L["Direct model REST"]
    UI["Confirmed control actions"] --> LC["Launcher control API"]
    LC --> AG["Mortal agent processes"]
```

Read-plane sources are immutable from the Observatory. Control actions use the
launcher, carry authenticated session identity, and append their own audit
events. The control plane can launch, stop, or revise a mortal agent goal. It
cannot issue game commands, use administrator credentials, or mutate evidence.

The control plane exposes only three operations:

- launch a mortal run for a selected player with a reviewed task, model,
  limits, tool profile, and optional reset baseline
- stop a selected run through the launcher lifecycle
- propose a goal revision to the selected agent's goal channel

An Observatory launch is a persistent session, not one-turn automation. Its
optional first goal enters turn one through a dedicated persistent stdin mode.
The existing one-shot `--task-stdin` contract remains unchanged for automation.
After a completed turn, the agent waits for later instructions. The supervisor
stops an idle session after a configurable timeout, 30 minutes by default.

Launch presents the exact effective configuration and maximum spend before
confirmation. Goal revisions show the active goal, proposed replacement, and
delivery state. They require confirmation and become immutable session events.
Failure to deliver does not change the displayed active goal. Stop and launch
errors retain typed failure evidence and recovery guidance.

### Package shape

```text
week2_capable/observatory/
  observatory_api/
    app.py
    capabilities.py
    sources/
    queries/
    redaction/
  web/
    src/
      app/
      contracts/
      features/
      projections/
      visualization/
      workers/
  tests/
  pyproject.toml
  package.json
  README.md
week2_capable/bin/observatory
```

The exact split may change during the scaffold spike. Responsibilities must not
collapse into a single application module.

### Read API

A thin local Starlette API provides:

- same-origin access to gateway SSE and replay
- source capability discovery
- read-only aggregation across session, agent, benchmark, and knowledge data
- validated observatory queries
- incident-capsule export
- optional copilot mediation and spend policy
- static frontend serving for the installed launcher

The API does not duplicate or mutate session truth. It consumes gateway HTTP and
SSE instead of opening the gateway journal directly.

### Browser client

The client uses React, Vite, and strict TypeScript. Public contracts are
schema-generated or checked against one canonical schema to avoid handwritten
Python and TypeScript drift.

The event reducer:

- orders by `seq`
- deduplicates by `(session, seq)`
- detects gaps
- fills gaps through replay
- retains unknown event kinds
- produces the same state from live and replay input

Long replay, derived projections, layout, and comparison alignment run in Web
Workers. Disposable IndexedDB caches may accelerate reopening a session. Cache
keys include session, final sequence, schema version, and projection version.
The journal remains authoritative.

Markup is built with components. MUD and model text is always rendered as text
or tokenized ANSI components. Raw HTML injection is prohibited.

### Visualization engine

Two render paths are expected:

- SVG for small causal and journey graphs where rich interaction matters.
- Canvas or WebGL for atlas-scale graphs.

Sigma.js and Graphology are candidates for the atlas because they target
WebGL rendering of large graphs. Adoption depends on a measured spike using the
actual world size, keyboard and screen-reader fallbacks, bundle impact, and
maintenance status. The plan does not choose a graph library from a screenshot.

### Configuration and capabilities

Configuration controls:

- enabled data sources
- available workspaces and overlays
- diagnostic rules and thresholds
- retention and local cache
- redaction policy
- model access, evidence allowlist, and spend cap
- observer-truth visibility
- experimental features

One runtime registry describes every user-selectable gateway and agent feature:

- stable id, label, description, type, default, valid values, and dependencies
- whether the feature affects evidence, model input, gameplay, or cost
- whether it is safe for replay, requires reset, or requires a paid run
- the runtime version and digest that interpreted it

The runtime and experiment workbench consume the same registry. Unknown
registry entries remain inspectable and disabled until the current client can
render their type safely.

Capabilities are reported at runtime. A disabled or unavailable source produces
an explanation and setup action. Feature configuration is fixed for an
investigation export so results remain reproducible.

### Live-delivery prerequisite

The current gateway event hub receives callbacks from the `Journal` instance in
its own process. The MCP server and HTTP API can create separate journal
instances, which means SQLite replay may work while cross-process live delivery
does not.

Before observatory live work begins, a gate must prove that an event written by
the active MCP session reaches the API subscriber without polling races. The
implementation should either:

- host MCP and the event API with a shared journal and event hub, or
- make the API tail committed journal events safely across processes.

This is a correctness dependency, not an observatory workaround.

## Instrumentation health

The observatory must observe its own evidence quality.

The global status surface reports:

- connection state and last event age
- sequence gaps and replay recovery
- duplicate events
- subscriber drops
- unknown schemas and event kinds
- missing trace or wire references
- clock skew or unavailable duration
- source version and capability digest
- redaction failures
- stale projections

Charts display completeness alongside values. A cost curve with missing usage
events cannot look identical to a complete curve.

## Security and privacy

- Bind locally by default.
- Require explicit configuration for non-loopback access.
- Keep all sources and actions read-only.
- Redact at ingestion boundaries and again during export.
- Never expose MUD, model, or admin credentials to the browser.
- Treat model prompts, tool arguments, wire text, and player communication as
  potentially sensitive.
- Use allowlists for copilot evidence and query operations.
- Record copilot model, policy, token use, cost, and cited evidence.
- Apply a strict content security policy.
- Escape all untrusted text.

## Accessibility and performance

The target is WCAG 2.2 AA for product workflows.

- Meaning never depends on color alone.
- Focus is visible and never hidden by overlays.
- Every graph has a keyboard path and structured tabular alternative.
- Reduced motion removes animated travel and chart transitions.
- Screen-reader labels state uncertainty, source layer, and selection.
- Zoom does not hide essential controls.
- High-density views retain readable text and touch targets.

Performance budgets are defined before implementation:

- live event to visible update at p95
- replay events processed per second
- interaction frame time during long sessions
- initial bundle size
- memory after a full J2 replay
- atlas pan and zoom frame rate at actual world size

Virtualization, workers, level of detail, and incremental projection are used
only where measured budgets require them.

## Question coverage

Product acceptance follows investigation questions, not the presence of a
widget.

| Question | Primary space | Required evidence | Acceptance gate |
| --- | --- | --- | --- |
| What is the selected player doing now? | Live | registry, agent lifecycle, goal, gateway stream, player state | a real journey grows without manual refresh |
| Where is the player and how certain is that location? | Live | room, exits, position candidates, confidence, wire refs | duplicate titles remain distinct and explainable |
| Why did this action happen? | Sessions | model request, response, tool call, command, wire, parse, state | one selection traverses the complete causal chain |
| Why did the agent stop? | Sessions | goal revisions, final claim, stop reason, verified state | the answer uses only the selected session and cites its evidence |
| What did this turn cost and what progress did it buy? | Sessions | usage, rate snapshot, context, action, milestone | a cost point opens the billed response and outcome |
| What evidence is missing or stale? | Sessions | source health, sequence gaps, field provenance, observed time | affected conclusions name their capture gaps |
| Which system design performs better? | Experiments | immutable definition, reset receipt, samples, predicates, usage | aggregates and outliers open their full Sessions runs |
| Can a new runtime feature be tested without UI code? | Experiments | versioned feature registry and effective run config | a registered typed flag appears and is persisted automatically |
| What has this player learned across sessions? | Knowledge | per-player assertions, CDC, provenance, snapshots | a fact opens every supporting and contradicting observation |
| Where does learned state differ from truth? | Knowledge | learned assertions and quarantined observer truth | Learned, Truth, and Diff preserve source separation |
| Can an investigator ask in plain language? | Any selected space | typed query plan and cited returned evidence | model-disabled questions still work and every claim opens |
| Can another person reproduce the diagnosis offline? | Sessions | sanitized evidence prefix, source versions, notes, gaps | an exported capsule reopens without credentials or live services |

## Verification strategy

### Contract and reducer tests

- live and replay prefixes produce identical projections
- reconnect produces no gaps or duplicates
- unknown event kinds survive
- missing and partial evidence stays explicit
- observer truth cannot enter agent-facing projections
- source versions invalidate derived caches

### Component tests

Vitest and React Testing Library cover:

- workspace coordination
- evidence citations
- diagnostic explanations
- unavailable and stale states
- keyboard navigation
- reduced motion
- copilot query-plan review
- malicious text and ANSI rendering

### End-to-end tests

Playwright covers:

- start from a fresh clone
- connect to a replay and a live session
- switch between two concurrent players without crossing evidence
- pause, scrub, inspect evidence, and return to live
- unfold a session from turn to wire source and ask why at the paused moment
- recover from a dropped SSE connection
- investigate a false completion
- compare two runs at their first divergence
- define an experiment from the feature registry, verify reset, watch one
  sample, stop it, and open aggregate and per-run results
- change Knowledge level of detail, inspect provenance, snapshot, reset, and
  restore without deleting history
- ask a deterministic and a model-disabled question
- export and reopen an incident capsule

UI work is verified from rendered pages at desktop, narrow, high-contrast, and
reduced-motion settings.

### Performance and visual tests

- replay the longest recorded session
- render the actual CircleMUD world scale
- profile main-thread blocking and memory
- capture stable visual states for key workspaces
- test with intentionally incomplete and contradictory evidence

## Incremental build plan

Each increment ends with tests, a rendered UI check, an accurate package README,
and a journal entry only when the work yields an instructor-worthy lesson.

### Increment 0: Evidence and live-delivery gate

- prove active MCP events reach SSE subscribers
- freeze the event and capability contracts
- define projection and query schemas
- create fixtures for complete, partial, ambiguous, and unknown evidence

Exit gate: one fixture and one active session produce gap-free, equivalent live
and replay prefixes.

### Increment 1: Product shell

- scaffold the read API and strict TypeScript client
- add the installed launcher and fresh-clone setup
- implement capability discovery and source health
- establish tokens, typography, layout, accessibility, and themes
- render the investigation workspace with representative fixtures

Exit gate: a fresh clone launches one polished read-only shell and accurately
reports available capabilities.

### Increment 2: Live and time travel

- player switcher, session selector, and global clock
- causal activity timeline
- pause, scrub, bookmarks, and return to live
- full player state, journey, cost, and instrumentation health
- Focus radius, Grow, and Lantern map modes
- follow, manual, and fit-selection camera modes
- room popover, condition glyphs, and evidence-gated objective beacon
- authenticated guidance, goal revision, pause, resume, and stop at the agent
  iteration boundary
- URL-addressable selection

Exit gate: every panel reconstructs the same state at every selected sequence,
and control can target only the selected live agent session.

### Increment 3: Sessions investigation and diagnostics

- unfoldable session sequence and automatic, event, turn, and milestone replay
- causal waterfall
- evidence lens
- belief-versus-reality workspace
- cost and context lenses with clickable source attribution
- paused-moment "Ask why"
- false-completion, ambiguity, loop, stall, and parse diagnostics
- structured search and saved views

Exit gate: the recorded J2 false completion can be diagnosed from claim to exact
evidence without reading raw files.

### Increment 4: Living world

- journey and neighbourhood views
- belief, inference, and truth layers
- uncertainty and parse-miss overlays
- duplicate-room and candidate-position interaction
- atlas renderer spike at actual world size

Exit gate: duplicate room titles remain separate and the selected candidate set
is explainable from exits and neighbourhood evidence.

### Increment 5: Experiments comparison and counterfactual replay

- semantic run alignment
- first-divergence workflow
- synchronized maps and timelines
- parser and rendering counterfactual projections
- attention-economics measures

Exit gate: the raw, minimal, and full J1 experiments can be compared without
manually joining reports or aligning turns.

### Increment 6: Grounded investigation copilot

- deterministic saved questions
- typed observatory query language
- visible query plans and evidence citations
- optional direct-REST model translation and summary
- redaction, permissions, and spend controls
- copilot accuracy and cost evaluation corpus

Exit gate: every answer is reproducible from its query and citations. Disabling
the model preserves the core investigation workflow.

### Increment 7: Knowledge and incident workflow

- cumulative per-player knowledge overview, frontier, entities, player, and
  progression
- room, cluster, and zone levels of detail
- entity search, filters, grouping, pagination, mobile sightings, and
  simultaneous instances
- Learned, Truth, and Diff layers
- snapshot, append-only reset, and restore
- incident capsules
- investigator annotations
- sanitized export and offline reopen
- diagnostic history across sessions

Exit gate: a session investigation can be handed to another person without the
live MUD, credentials, or undocumented local state.

### Increment 8: Product hardening

- performance budgets and optimization
- accessibility audit
- failure injection for gaps, corruption, and unavailable sources
- responsive and high-contrast polish
- feature-flag and configuration coverage
- reference-floor audit

Exit gate: all required workflows pass end-to-end, rendered, accessibility, and
performance gates.

### Increment 9: Universal evidence graph

- index every captured record, field, and retained scalar value without
  dropping unknown data
- correlate evidence by session, turn, tool ID, trace ID, sequence, time, room,
  command, model call, benchmark attempt, and configuration version
- render agent request, context, response, reasoning, tool arguments, tool
  result, gateway command, wire frames, parser output, and state change
- preserve the exact sanitized source record beside each meaningful rendering
- provide session, model, limits, duration, instrumentation, error, and
  completeness views
- make every timeline event, room, diagnostic, cost point, comparison sample,
  message, and source-health signal an entry point into the same graph
- allow pivots across causal, chronological, spatial, model, tool, gateway,
  cost, quality, configuration, and raw-source dimensions
- retain navigation history, breadcrumbs, linked filters, and stable URLs so an
  investigator can move down, up, or sideways without losing context
- provide a schema-aware fallback inspector for new event kinds and fields
  before a specialized renderer exists

```mermaid
flowchart TB
    E["Captured evidence graph"] --> T["Time"]
    E --> C["Causality"]
    E --> S["Source and process"]
    E --> W["World and entities"]
    E --> K["Cost and context"]
    E --> M["Model and messages"]
    E --> G["Gateway and wire"]
    E --> Q["Quality and completeness"]
    E --> V["Configuration and versions"]
    T <--> C
    C <--> M
    M <--> G
    G <--> W
    K <--> C
    Q <--> S
```

The same evidence can be viewed at several levels:

1. outcome and session
2. milestone and turn
3. causal span
4. individual message, tool, gateway, parse, or state event
5. exact sanitized source record and retained fields

Exit gate: automated coverage proves that every captured record, field, and
retained value has a meaningful renderer or the schema-aware fallback. From any
dimension, an investigator can reach the exact source, move up or down the
containment hierarchy, and pivot to every correlated dimension without a dead
end. Missing correlations are counted and displayed as capture gaps.

### Increment 10: Live journey cockpit

- join live agent events with the active gateway session
- animate the recorded journey as rooms, exits, actions, and costs arrive
- show current goal, plan, model state, tool action, result, vitals, and position
- retain the recent trail, frontier, unresolved candidates, and parse misses
- distinguish waiting, disconnected, replaying, paused, and genuinely idle
- let a live diagnostic pause the view and open its triggering evidence

The central canvas must communicate progress without requiring the side rail.
An empty map is an explicit source or session state, never the normal live view.

Exit gate: one real agent journey visibly builds the map and causal timeline
from an empty session through several verified state changes.

### Increment 11: Cost and context intelligence

- add cumulative and marginal cost curves
- split fresh input, cache read, cache write, and output tokens
- show prompt size, context occupancy, amplification, calls, latency, and retries
- connect spend to rooms, actions, milestones, loops, corrections, and stalls
- identify repeated context and cost after the last verified progress
- explain every cost measure and its completeness
- support cost-focused saved questions and drill-down

```mermaid
flowchart LR
    U["Usage evidence"] --> T["Turn cost"]
    T --> A["Action"]
    A --> M["Milestone or no progress"]
    M --> E["Efficiency measures"]
    E --> D["Cost diagnostics"]
    D --> X["Exact prompt and response evidence"]
```

Exit gate: the J2 run reveals where money was spent, what progress it bought,
and which turns added cost without adding verified information.

### Increment 12: Benchmark workbench

- describe journeys in plain language before showing internal IDs
- generate controls from the versioned runtime feature registry
- select objective, start state, model, tool profile, rendering, parser, limits,
  repetitions, stop criteria, and spend cap
- preview the exact controlled variables and estimated maximum spend
- reset and verify the same baseline before every repetition
- run only validated benchmark definitions through a separate controlled runner
- stream attempt progress, cost, state, errors, and completion criteria
- watch one active sample at a time
- save immutable experiment definitions beside results
- compare aggregate distributions, individual attempts, outliers, setup
  failures, and first divergences
- support rerun, fork, and one-variable-at-a-time experiment creation
- open every sample and metric in Sessions

The observatory remains read-only for gameplay. Benchmark execution is an
explicit experiment action with a confirmation boundary and a separate process.

Exit gate: a user can define, run, and compare a small budgeted experiment
without editing files or knowing repository-specific benchmark names.

### Increment 13: Reference-floor workflow audit

The audit verifies questions and workflows, not route names.

| Information need | Required path |
| --- | --- |
| Session and run overview | Overview to exact session detail, then any correlated dimension |
| Live transcript | Live event to sanitized source message, turn, action, and world change |
| Tokens, context, and cost | Cost curve to one billed response, prompt, cache class, and progress result |
| Operation spans | Model turn to tool, gateway, wire, parse, state, and back |
| Test and benchmark results | Experiment definition to cohort, attempt, turn, and evidence |
| Manager and Telnet logs | Gateway span to redacted wire frames, command, parse, and caller |
| Errors and health | Failure state to cause, affected evidence, and recovery |
| Knowledge and world | Place or entity to every supporting observation and visit |
| Player progression | Change to the exact event, action, and evidence that caused it |
| Dropped output | Completeness measure to missing sequence, source, and affected conclusions |

Exit gate: every confirmed reference-floor information need is demonstrated by
an end-to-end test and a rendered workflow. Innovative views add capability
above this floor, they do not substitute for it.

## Scope and priority

The recommended Week 2 priority is:

1. Make the evidence path trustworthy and live.
2. Build Live, Sessions replay, and belief-versus-reality.
3. Add the living journey map and automatic diagnostics.
4. Build Experiments because it closes the loop on current measurements.
5. Add the deterministic query engine and a narrow grounded copilot.
6. Expand knowledge and atlas features as their data source becomes ready.
7. Harden and polish continuously, with a final focused pass.
8. Complete evidence drill-down, cost intelligence, and the benchmark workbench
   before calling the product complete.

The full atlas, generalized cross-session intelligence, and broad copilot are
larger than the observability core. They should not block the first useful
product, but adjacent foundations should be built now when deferral would force
a contract or storage rewrite.

The flagship experience is not negotiable: belief-versus-reality, causal
evidence, and time travel must arrive before the product is called an
observatory.

## Table stakes to cover

The instructor reference was inspected from its current source at commit
`54ce7324fea32c25b8e38db3fc2f430888018fa2`. These features are a floor, not the
navigation model.

### Confirmed reference capabilities

- dashboard
- sessions and session detail
- live transcript through SSE
- timing, duration, tokens, context, cost, model, and tool counts
- operation spans
- test reports, pass rates, failure modes, cost, and calls
- manager and Telnet logs
- errors
- change log
- health
- player and profile selection
- knowledge overview
- rooms and map
- entities and frontier
- player sheet and progression
- belief, provisional, one-way, unwalked, displaced, and player-position map
  states
- dropped-output ratio

### Unconfirmed or stale reference claims

- The initial reference plan mentions dedicated diff and reshaped views, but a
  current dedicated route was not confirmed.
- The initial plan mentions standalone ground-truth world pages, while the
  current application exposes a knowledge map.
- Production authentication, multi-user access, and remote deployment posture
  were not confirmed.

The observatory should cover the operational questions behind these features
through its unified evidence model. It should not reproduce the reference's
framework, log-file boundaries, or page taxonomy.

## Quality bar

| Requirement | Plan |
| --- | --- |
| Best practice | Evidence-first, typed, read-only, accessible architecture |
| One responsibility per module | Sources, queries, projections, diagnostics, and visualization are separate |
| Typed public interfaces | Python type hints, canonical schemas, strict TypeScript |
| No markup concatenation | React components and tokenized safe text rendering |
| UI rendered for verification | Every UI increment includes rendered checks |
| Pinned dependencies | Each adopted dependency is pinned and justified |
| New Python tests | Pytest |
| Observatory tests | Vitest, React Testing Library, and Playwright |
| No committed build output | Frontend build and caches remain ignored |
| Documents match disk | README follows implementation, this file describes future work |

## Design influences

- OpenTelemetry trace and semantic-convention concepts guide correlation and
  vocabulary: <https://opentelemetry.io/docs/concepts/>
- Grafana trace-to-log correlation demonstrates evidence navigation across
  signals: <https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-logs/>
- Sigma.js provides a candidate WebGL path for large graph rendering:
  <https://www.sigmajs.org/docs/>
- WCAG 2.2 guides color-independent meaning and visible interaction state:
  <https://www.w3.org/TR/WCAG22/>
