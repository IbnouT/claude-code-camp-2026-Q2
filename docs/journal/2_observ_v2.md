# Week 2 Technical Documentation

## Technical Goal

Make the agent observable before making it more capable. Week 1 produced a
working loop, live TUI, finished-run viewer, context management, and cost
accounting. Week 2 must reveal what happens below and around that loop:

- what the model was asked and what it returned
- what each tool requested and what the gateway executed
- what crossed the Telnet connection, including unsolicited game events
- what the parser inferred and what remained uncertain
- what the agent believed, what the game evidence supports, and what the run cost
- how to follow the same evidence live and replay it afterwards

The result should let someone start with a complete journey, then reach the
exact retained event that explains any cost, delay, decision, state change, or
outcome.

## Technical Uncertainty

- I am uncertain whether more instrumentation will explain behaviour or merely
  create more logs to search.
- I am uncertain how much MUD output can be typed deterministically without a
  model call.
- I am uncertain whether reducing tool-result size actually reduces journey
  cost, since less context may also make the agent take a worse path.
- I am uncertain how to compare the agent's claimed result with game evidence
  without turning one interpretation into false truth.
- I am uncertain whether one interface can remain understandable while joining
  model, agent, tool, gateway, Telnet, MUD, state, time, and cost evidence.

## Technical Hypotheses

- A gateway that owns the Telnet wire will make runs replayable and expose
  failures that agent logs alone cannot prove.
- Rules close to the wire will type most common game output more cheaply and
  consistently than another model call.
- Tool-result size will be a major driver of run cost.
- Raw evidence and derived interpretations must remain separate, with missing
  or ambiguous evidence kept visible.
- An Observatory organized around one session timeline will be more useful than
  separate viewers for logs, maps, costs, and experiments.

## Technical Observations

### 1. Owning the wire exposed the first missing layer

Week 1 could show the agent's recorded tool calls and model exchanges, but it
could not independently prove everything the MUD sent or correlate an action
through every boundary. We replaced the external MUD manager with a Python
gateway that owns login, Telnet transport, command execution, parsing, and an
append-only SQLite journal.

- The journal retains raw wire evidence, typed observations, trace identities,
  timestamps, and sequence numbers in one per-session record.
- A committed journal was replayable but initially not live across processes.
  Writer callbacks ended at the writer process. Sequence cursors over the
  durable journal made live delivery and replay use the same contract.
- Grouping 25 direct tools into fewer tools did not shrink the model surface.
  The grouped schema measured 7,494 bytes against 6,290 bytes for the direct
  surface. Tool count alone was therefore not a useful optimization target.
- ANSI colour was usable protocol evidence. Colour-aware rules typed 2,644 of
  3,067 recorded lines without a model. The remaining 423 lines stayed linked
  to their raw evidence instead of being silently guessed.

Gateway architecture and evidence boundaries:
[gateway README](../../week2_capable/gateway/README.md).

### 2. Reproducible benchmarks corrected plausible but wrong conclusions

The benchmark work began by trying to reproduce the Week 1 working figure of
448 tool calls. The retained sessions supported two different counts: 451
executed calls and 447 calls visible in a later prompt. Four terminal calls
never reached another prompt, and the value 448 had no reproducible counting
rule.

The first bakery comparison also produced a tempting false conclusion. One
full-result run succeeded while raw and minimal runs failed, suggesting that
more metadata helped. A later raw run was invalid because another client left
the character inside the bakery, so reset had not established the promised
starting state.

The corrected experiment reset and verified the character before model spend,
then ran ten journeys for each result form:

| Result form | Success | Mean cost | Mean calls |
|---|---:|---:|---:|
| Raw | 10/10 | $0.03092625 | 13.0 |
| Minimal | 10/10 | $0.03975862 | 19.9 |
| Full | 10/10 | $0.03152708 | 13.8 |

- Full results contained 59.8 percent more bytes than raw over identical
  observations, but raw and full journey costs overlapped.
- Minimal used 53.1 percent more calls and cost 28.6 percent more than raw in
  this sample.
- Path length dominated the small payload difference. Ten repeated runs
  overturned the conclusion suggested by one sample.

The full methods, exclusions, measurements, and caveats are in
[Week 2 experiments and findings](../reports/week2_experiments.md).

### 3. A completed agent turn was not proof of a completed journey

The long navigation probe asked the agent to find the Massive Minotaur. It
visited 17 distinct positions and stopped after 90 tool calls while reporting
completion, but no retained game observation satisfied the goal predicate.

- The run cost $0.21086010, about 6.7 times the full-result bakery mean.
- Repeated junctions showed that movement inefficiency increased both the
  number of calls and the cost of later calls as the prompt grew.
- Duplicate room titles left the final position ambiguous. The tracker
  preserved both candidates instead of inventing one location.
- Per-response cost fields summed to $0.0499 because they omitted cache-read
  charges. Repricing from retained usage classes reconciled the response curve
  exactly to the authoritative turn total.

This run changed the product question. The important result was not merely
that the agent failed. It was that agent belief, game-grounded outcome,
position confidence, path repetition, and cost could disagree while each
remained individually plausible.

### 4. Multiple players made evidence identity a correctness boundary

Running two agents at once required every artifact to belong to one player and
one session. A global "current session" or directory scan would allow evidence
from one character to appear under another.

- The launcher registry became the source of session identity and lifecycle.
- Each player owns separate session evidence, knowledge, cost, and control
  state.
- A kernel-held character lock prevents two agents from driving the same
  character and disappears automatically after a crash.
- Reset uses a short-lived administrator child, reconnects the mortal session,
  and verifies the resulting state field by field.
- A partial reset quarantines the session because the MUD cannot provide a real
  rollback.

The isolation and reset contract is described in
[the multiplayer plan](../plans/week2_observ/multiplayer.md).

### 5. The first Observatory problem was organization, not missing panels

The evidence sources quickly outgrew a traditional log viewer. Separate views
could each be correct while leaving the reader to reconstruct causality by
hand. The Observatory therefore uses one selected player, session, evidence
prefix, and subject across Live, Sessions, Experiments, and Knowledge.

The first feature-rich frontend still failed as an observability surface. It
gave capabilities space without preserving a clear journey hierarchy or the
binding visual language. The presentation was rebuilt while retaining the
typed API, evidence contracts, capability transport, dependencies, and test
harness. That separation was valuable: evidence semantics could remain stable
while the product surface changed completely.

The Sessions design also borrowed a small set of proven interaction ideas:
[Honeycomb](https://docs.honeycomb.io/reference/honeycomb-ui/query/trace-waterfall)
keeps hierarchy, time, and selected detail together,
[Datadog](https://docs.datadoghq.com/tracing/trace_explorer/trace_view/)
focuses a subtree without changing its source trace,
[Grafana](https://grafana.com/docs/grafana/latest/visualizations/explore/trace-integration/)
pivots between correlated signals, and
[Langfuse](https://langfuse.com/docs/observability/overview) treats model calls
and tools as nested measured work. The useful lesson was one execution spine
with progressive drill-down, not copying any product's dashboard.

- Source health belongs beside the claim it can weaken, not as a destination
  in the global header.
- Wire, Parsed, Rendered, Believed, and Truth are separate evidence forms.
  Missing forms remain visible rather than being filled by another layer.
- The cumulative player knowledge store and a single-session reconstruction
  disagree by construction. The player store is authoritative for cumulative
  knowledge, while the run projection is a labelled session lens.
- Natural-language questions compile to typed, read-only operations with an
  explicit player, session, and temporal scope. Optional model translation
  does not receive the evidence and cannot widen that scope.

Current product boundaries and implemented capabilities:
[Observatory README](../../week2_capable/observatory/README.md).

### 6. Live observation exposed events the command loop did not own

Watching real sessions found several gaps that request-response tests did not
show:

- Combat text and prompt vitals can arrive between commands. Capturing only
  command replies left both the fight stream and health stale.
- Administrative relocation looked like learned traversal until reset and
  control receipts became explicit continuity boundaries.
- Prompt vitals, score maxima, tool calls, and response economics can all be
  true at different moments. Each value needs its own observation sequence.
- A completed model turn originally stopped the observed session because the
  launcher reused a one-shot task path. A persistent host now waits for another
  goal or message and stops only through explicit control or a configurable
  idle timeout.
- Accepting an operator message was not the same as delivering it. An idle
  agent required a wake path so a retained Goal or Nudge would reach another
  consumption boundary exactly once.

These failures made replay part of Live rather than a separate after-the-fact
feature. A historical prefix and the latest retained snapshot coexist so the
reader can step backward, step forward, or return to live without erasing
future landmarks.

### 7. A universal session needed one story and a stable temporal identity

Launcher runs and experiment runs now open through the same recorded-session
projection. The useful structure was the execution hierarchy, while cost and
time stayed on the records that actually own them.

- Counting response cost again on turn-end records doubled believable-looking
  totals. Response ownership made each turn and run sum reconcile.
- Trace correlation placed most gateway evidence under its agent iteration.
  Records without support stay in an explicit run-scoped group.
- The full wire body is useful at the bottom of an investigation, but noisy at
  the top. It now loads only after selecting one integrity-checked wire record.
- The first pane-based workspace still made the reader reconcile summaries,
  rows, filters, and an inspector. Replacing it with one chronological Story,
  plus linked Map and Cost projections, made the evidence hierarchy readable
  before any drill-down.
- Multiple goals exposed a subtler identity bug: iteration numbers restart
  inside each turn. A regression fixture with turn 1 iteration 1 and turn 2
  iteration 1 would merge under a numeric key. Selection and replay now use the
  turn and iteration together, while applied Goals start epochs and Nudges
  remain attached to the active epoch.
- Natural-language Ask cannot be represented by keyword-triggered evidence
  lookup. A question about an objective needs model-planned retrieval,
  deterministic evaluation, grounded synthesis, and verified citations.
- Searching nested request bodies made an old room name match most later
  iterations through accumulated history. Story search now uses readable
  labels and previews, while exact bodies remain available in drill-down.

The evidence inventory and interaction contract are in
[the Sessions plan](../plans/week2_observ/observatory/sessions.md).

### 8. Cohort means needed their variability and exact sessions

The retained J1 means looked decisive until standard deviation and individual
samples were kept beside them. Minimal used more calls and cost on this
journey, while raw and full overlapped within their observed variation.

- Every aggregate now opens the sample sessions that produced it.
- Registered configuration states what the installed runner can vary.
  Unsupported dimensions remain observable without pretending to execute.
- Representative paths explain where behavior differed, while the repeated
  cohort establishes whether that example is typical.

The evidence and execution boundaries are in
[the Experiments plan](../plans/week2_observ/observatory/experiments.md).

### 9. Display policy could not be retention policy

Result modes deliberately change what the model sees, while REPL, TUI, and
Observatory views summarize for different readers. Treating either choice as a
logging boundary erased the source needed to explain later behaviour.

- Model request, provider response, and normalized content are now distinct.
- Tool results retain original MCP text, rendering, truncation, and model input.
- MUD evidence retains bytes, decoded text, normalized parser input, typed
  observations, and projected state as separate linked stages.
- An aggregate that kept only matching rows destroyed the explanation around
  them. Aggregate focus now retains the enclosing iteration and causal chain.
- Older recordings name missing stages instead of implying complete evidence.

## Technical Conclusions

- The gateway hypothesis held. Owning the wire made raw evidence, typed
  observations, live delivery, and replay part of one sequence.
- Deterministic parsing worked for most recorded lines, while retaining the
  residual made its limits measurable.
- The tool-result cost hypothesis did not hold in its simple form. Payload size
  mattered, but the behaviour caused by that payload changed total journey cost
  more.
- More logs alone did not solve observability. Useful explanation required
  stable identity, causal and temporal correlation, explicit provenance, and
  drill-down from summaries to source evidence.
- Belief and truth cannot be collapsed into one result. Agent claims, game
  predicates, parser confidence, cumulative knowledge, and observer truth need
  distinct labels and relationships.
- The main uncertainty still open is whether repeated experiment runs can stay
  comparable while exposing enough configuration to explain their differences.

## Key Takeaway

Observability became useful when every summary could lead back through the
agent, model, tool, gateway, Telnet, and MUD boundaries to the retained evidence
that supports it.
