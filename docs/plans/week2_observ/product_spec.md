# Observatory product specification

This document is the interaction contract for the Observatory. The architecture,
evidence model, and build order remain in `observatory.md`. The HTML mockups
remain the visual references.

An implementation is in scope only when it satisfies a contract below.

```mermaid
flowchart LR
    Context["Player context"] --> Live["Live\nOperate now"]
    Context --> Sessions["Sessions\nExplain what happened"]
    Context --> Experiments["Experiments\nTest a system change"]
    Context --> Knowledge["Knowledge\nInspect learned state"]

    Live --> Evidence["Evidence graph"]
    Sessions --> Evidence
    Experiments --> Evidence
    Knowledge --> Evidence

    Evidence --> Detail["Stable detail route"]
    Detail --> Source["Exact sanitized source"]
```

## Shared context and navigation

Goal: preserve orientation while avoiding a crowded universal toolbar.

| Concern | Contract |
| --- | --- |
| Header | Full brand, four spaces, player selector, theme, and only the controls relevant to the active space |
| Player | Always explicit, switching invalidates incompatible session, selection, and control state |
| Session | Present in Live and Sessions, absent where session context does not apply |
| Selection | Player, session, time, subject, and lens are encoded in the URL when meaningful |
| Theme | Dark and light preserve hierarchy, semantics, contrast, and terminal legibility |
| Narrow screens | One focused pane, stable routes, sheets, and explicit internal scroll owners |
| Loading | Empty, loading, stale, reconnecting, unavailable, and incomplete remain different states |

Visual references:

- `design_system.html`
- `sessions_unified.html`

Acceptance:

- A destination does not introduce a competing shell.
- A control is absent when its action has no valid target.
- Switching context cannot leak evidence or drafts between players.
- The root page scrolls when content exceeds the viewport.

## Live journey cockpit

Goal: understand what an active agent is doing and intervene safely.

Primary questions:

- Where is the agent now?
- What is it trying to accomplish?
- What changed on the last turn?
- Is it progressing, looping, fighting, waiting, or disconnected?
- What is the current cost and remaining spend?

Information hierarchy:

1. connection, lifecycle, freshness, and objective
2. living world with current position and active event
3. causal activity and live economics
4. self-raising attention and instrumentation issues
5. contextual evidence and safe agent control

Interactions:

- select an authenticated live session
- pause visual following without pausing the agent
- scrub the observed prefix and return to live
- select a room, event, cost point, tool call, or diagnostic
- open evidence without losing the live selection
- guide, revise, pause, resume, or stop the selected agent

Evidence:

- gateway connection and session lifecycle
- agent goal revisions and control acknowledgements
- model requests, responses, usage, tools, wire, parse, and rendered state
- combat, vitals, progression, inventory, and room observations
- causal sequence and source freshness

States:

- active, waiting, paused, idle, replaying, disconnected, ended, stale, and ambiguous
- combat is an explicit live state with its own activity and vitals treatment
- position confidence distinguishes observed, inferred, candidate, and unknown

Safety:

- control targets only the selected authenticated mortal session
- every mutation previews target, insertion point, tools, model, and maximum spend
- idempotency and expected sequence prevent stale control
- operator guidance never appears as agent reasoning or game truth

Responsive behavior:

- the world remains the main pane
- the attention rail becomes a bottom sheet or stable detail route
- all live metrics and controls remain reachable

Visual references:

- `live_cockpit.html`
- `map_modes.html`
- `map_detail.html`
- `player_status.html`

Acceptance:

- A deterministic replay produces the same visible prefix as live delivery.
- A real agent action updates the world, activity, cost, tokens, and status.
- A fight is visible as combat, not merely as another text event.
- An invalid control action explains why it cannot be sent.

## Sessions investigation

Goal: explain a recorded journey from outcome down to exact source bytes.

Primary questions:

- Why did the agent take this action?
- Why did it stop?
- Where did time and money go?
- Which evidence supports or contradicts the conclusion?

Information hierarchy:

1. selected run, outcome, objective, totals, and completeness
2. coordinated spatial and temporal lenses
3. sequence, cost, diagnostics, and evidence lenses
4. stable detail route for a selected span or record
5. exact sanitized source and hierarchy navigation

Interactions:

- discover, filter, and select a run
- load sanitized offline evidence
- select by room, turn, trace, event, cost point, or diagnostic
- synchronize map, sequence, cost, and evidence
- expand iterations, model calls, tools, hooks, and gateway operations
- move up to the containing turn and session or sideways to related evidence
- annotate, bookmark, export, and reopen an incident capsule

Evidence dimensions:

- causal, chronological, spatial, model, tool, gateway, cost, quality,
  configuration, and source

Visual references:

- `sessions_unified.html`
- `sessions_replay.html`
- `session_sequence.html`
- `session_detail.html`
- `cost.html`

Acceptance:

- Every captured record, field, and retained value has a meaningful renderer or
  schema-aware fallback.
- No drill-down route ends without source, ancestry, or an explicit capture gap.
- Unrelated benchmark evidence never appears in a normal session explanation.
- Direct URLs restore the same player, session, selection, time, and lens.

## Evidence inspector

Goal: preserve the distinction between bytes, interpretation, presentation,
belief, and privileged truth.

Forms:

| Form | Meaning |
| --- | --- |
| Wire | Sanitized protocol bytes and framing |
| Parsed | Typed fields derived from wire or local events |
| Rendered | What the agent or operator was shown |
| Believed | Agent memory, inference, or final claim |
| Truth | Explicitly configured observer truth, quarantined from agent input |

Interactions:

- switch forms without changing the selected evidence identity
- open derivation method, parser version, confidence, residual, and source
- pivot to containing hierarchy and correlated records
- see missing forms as missing rather than empty

Acceptance:

- Every displayed value identifies its form and source.
- Truth cannot enter agent context or mortal control.
- Unknown event kinds remain inspectable through the fallback renderer.

## Cost and context intelligence

Goal: connect spend and attention to useful progress.

Measures:

- reconciled total and cumulative cost
- marginal cost by response and since the last milestone
- fresh input, cache read, cache write, and output tokens
- cached versus uncached economics
- context composition by token class
- cost per room, objective step, successful action, and resolved ambiguity
- cost spent in loops, corrections, and stalled work
- information gain and progress per turn

Interactions:

- select a cost spike and open the billed response
- pivot to prompt, action, observed outcome, milestone, and usage record
- filter by model, tool, category, room, objective, and time range
- compare alternative configurations with identical accounting

Visual reference:

- `cost.html`

Acceptance:

- Incomplete usage cannot render as an authoritative total or curve.
- Rates and usage remain separate retained evidence.
- Every aggregate opens its contributing responses and exclusions.

## Diagnostics

Goal: turn suspicious behavior into an evidence-backed investigation.

Required diagnostics:

- false completion
- belief divergence
- position ambiguity
- confusion loop
- progress stall
- parse degradation
- corrective-call cluster
- stale action
- context churn
- instrumentation gap

Each diagnostic contains:

- plain-language issue and consequence
- severity, state, version, and threshold
- exact evidence and competing explanations
- affected conclusions
- resolution state and related occurrences

Acceptance:

- A diagnostic never invents a benchmark relationship.
- Session diagnosis uses only the selected session unless the user explicitly
  asks for comparison.
- Missing correlation appears as a capture gap.

## Experiments workbench

Goal: define, validate, run, watch, stop, resume, and compare controlled tests.

Workflow:

```mermaid
flowchart LR
    Define --> Validate
    Validate --> Confirm["Confirm config and maximum spend"]
    Confirm --> Run
    Run --> Watch["Watch one live sample"]
    Run --> Stop
    Stop --> Resume
    Run --> Compare
    Compare --> Fork["Fork one variable"]
```

Definition:

- plain-language objective and verified predicate
- starting state and reset strategy
- two or more arms
- model, tools, prompt, memory, context, policy, and registered feature flags
- repetitions and six stop criteria
- spend cap and maximum-spend preview

Execution:

- validate before paid work
- reset and verify digest before every sample
- keep setup failures separate from agent outcomes
- watch one sample without losing queue control
- stop and resume deterministically

Comparison:

- success, distribution, outliers, exclusions, cost, progress, turns, and failures
- first semantic divergence
- alignment by room, tool, objective milestone, and verified state
- every sample links to its Sessions run

Visual reference:

- `experiments.html`

Acceptance:

- A registered typed feature appears without hand-built form code.
- Effective configuration and maximum spend appear before confirmation.
- Fork changes one variable and preserves provenance.
- A fixed benchmark result is evidence, not a substitute for the workbench.

## Knowledge

Goal: inspect what each player learned without confusing belief with truth.

Lenses:

- overview
- map
- entities
- progression
- snapshots
- history

Content:

- learned facts, truth, and diff
- assertions, supporting observations, and contradictions
- frontier, candidate duplicates, and unverified edges
- player progression, vitals, inventory, and entity sightings
- snapshots, append-only reset, restore, and parser rebuild history

Interactions:

- search rooms, zones, entities, assertions, and observations
- move from a fact to every support and contradiction
- use semantic zoom from atlas to zone to room
- keep mobile or respawning sightings distinct
- create a verified snapshot before reset
- restore by appending history rather than rewriting it

Visual references:

- `knowledge.html`
- `knowledge_entities.html`
- `knowledge_map_dense.html`
- `map_modes.html`
- `map_detail.html`
- `player_status.html`

Acceptance:

- Knowledge is isolated per player.
- Duplicate titles remain separate until evidence resolves them.
- Reset and restore link to verified snapshot content.
- Large maps avoid one DOM node per room and meet the measured render budget.

## Ask and structured search

Goal: answer natural-language and exact queries with visible evidence.

Placement:

- Live: ask about the selected live run
- Sessions: ask or search the selected recorded run
- Experiments: search definitions, jobs, samples, and comparisons
- Knowledge: search learned entities, places, facts, and history

Behavior:

- deterministic typed queries work without a model
- the visible plan names operations and scope
- answers cite exact evidence and disclose missing data
- saved questions keep stable URLs
- optional model translation produces only validated typed queries
- model spend is reported separately

Acceptance:

- The active player, session, time, subject, and lens define the query scope.
- A random live-session question cannot silently use unrelated benchmark evidence.
- Model translation cannot bypass validation or evidence citations.

## Instrumentation health

Goal: show whether a conclusion can be trusted, not merely whether a service is
running.

Placement:

- beside affected values and conclusions
- self-raising Live or Sessions status when abnormal
- experiment validation when required evidence is unavailable
- Knowledge freshness and history where retained state is incomplete

States:

- ready, disabled by policy, unavailable, reconnecting, stale, incomplete, and
  sequence gap

Acceptance:

- Healthy instrumentation does not consume permanent attention.
- An abnormal state names its source, age, affected evidence, and recovery.
- Capability discovery never pretends a disabled feature was not built.

## Incident capsules, annotations, and bookmarks

Goal: preserve and share an investigation without credentials or mutable
runtime dependencies.

Capsule content:

- selected range and causal subgraph
- versions, revisions, diagnostics, and annotations
- sanitized source references
- optional comparison
- renewed redaction validation

Acceptance:

- Offline reopen requires no credentials, provider, MUD, or hidden local state.
- Notes never alter original evidence.
- Bookmarks survive replay and retain stable evidence identity.

## Universal quality gates

Every feature passes:

- strict TypeScript or typed Python boundaries
- unit, component, and relevant end-to-end tests
- rendered desktop and narrow comparison against its mockup
- keyboard operation and focus restoration
- 200 percent zoom with explicit scroll ownership
- forced colors and reduced motion
- screen-reader names and non-color state semantics
- honest empty, stale, incomplete, unavailable, and failure states
- no credentials or unredacted secrets
- no invented evidence or silent cross-player correlation
