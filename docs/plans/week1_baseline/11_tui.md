# Step 11 · The Journey (TUI): plan

## Goal

Put a readable, live view of the player journey in front of the REPL. boukensha
plays the MUD, and the TUI shows the journey a human wants to watch: the current
room, humanized actions, the agent's thinking, and vitals. It is not the system
of record. The full technical trace lives in the JSONL log and the step-13 log
viewer. The plain REPL stays reachable with `tui=False` and `--no-tui`.

```
+-- header: server status · HP · Mana · Moves · Lv · ctx% · cost --+
+--[ Dashboard ]--[ Feed ]-----------------------------------------+
| Dashboard: MUD (current room, exits, description) + RECENT        |
|            (last 3 humanized actions, current thinking)           |
| Feed:      the journey as formatted cards, with in-tab search     |
+------------------------------------------------------------------+
| liveness spinner + humanized current action                       |
| boukensha> input                                                  |
+------------------------------------------------------------------+
```

## Scope

A readable journey view, deliberately simpler than a debug console:

- Two tabs. Dashboard (default) shows current state at a glance. Feed is the
  scrolling card history with in-tab search.
- Presentation by meaning: a framework-free presenter turns logger events into
  Room, Action, Thinking, and Combat cards. Plumbing events (prompt, iteration,
  token counts) produce no card, so the raw trace never reaches the TUI.
- The thinking view tracks the agent's latest text (per-iteration commentary
  and the final summary), so it never freezes on a stale summary.
- A combat box: windowed line-matched detection (real combat verbs), a
  red-bordered fight stream with the outcome, and a heartbeat edge pulse while
  a fight is live.
- Humanized actions everywhere: strip the MCP prefix and JSON, read verb plus
  key argument into a phrase.
- Header carries vitals and status (stance, hunger, thirst), a GOAL panel pins
  the latest instruction, and an animated unicode state badge reads the stance.
- A splash screen with the full config card, `/info` to reopen it, and a loud
  state when no tools register. The `mud` server is `required: true`.
- Real Esc cancellation, a command palette, `ctx%` window occupancy, the
  `Repl` composability surface, and `Logger.subscribe` consumption.

Out of this step, deferred with a trigger (journal): the world map and vnum-true
room identity (week 2, web visualizer), the findings engine (week 2).

## Deliverables

| File | Deliverable |
|---|---|
| `boukensha/journey/` | The MUD layer package: `present.py` (`Presenter`, `Card`, `humanize_action`, combat tracker, the de-noise boundary) and `parser.py` (`JourneyParser`, vitals/character/status for the header, findings engine dormant for week 2). Framework-free, unit-tested. Grouped now because week 2 adds the map renderer and findings UI here. |
| `boukensha/tui.py` | The Textual app: two tabs, header vitals, splash, cancellation, palette, feed search. The generic renderer over the journey layer. |
| `boukensha/repl.py` | The front-end surface, readers, and a `quiet` property so the TUI silences the REPL's own feed. |
| `boukensha/run_dsl.py` | `repl(tui=True)` wiring, lazy Textual import. |
| `examples/example.py` | Thin launcher: real TUI on a TTY, plain REPL without, `--replay` streaming a recorded real session. |
| `tests/` | Hermetic suite: presenter unit tests (humanizer, de-noise boundary, room parsing), the Tui frame driven headless, the real chain, the parser and world fixtures. |

## Design

### Two consumers of one event stream

`Logger.subscribe` fans events to the app thread via `post_message`. There, two
independent consumers read them: `JourneyParser` keeps vitals and character
state for the header, and `Presenter` turns events into cards. Keeping them
separate means the presenter owns display and the parser owns telemetry, and
neither grows the other's concerns.

### The de-noise boundary

The presenter is the single place that decides what a human sees. It emits a
card only for a room, an action, a thought, or a resolved fight. Token and
iteration plumbing produce no card. The response event carries the agent's text
(commentary or the final summary), which updates the thinking view but stays
out of the raw-trace category. Because the TUI renders only what the presenter
returns, the plumbing cannot leak in.

### Live thinking

The thinking view is driven by the agent's latest text from every response
event, deduped, skipping the tool-use placeholder the agent logs for a tool-only
turn. So it tracks the agent's current view and refreshes when the agent narrates
a new task rather than freezing on an old summary. The final routed reply carries
the same words, so the dedupe keeps it from doubling.

### Combat detection

Windowed and line-matched, the week0 approach. A result counts as combat only
for the lines matching a combat-verb pattern, so a fight is "on" only while such
lines keep arriving. A result with no combat lines and no death ends the fight,
which is what stops a login menu or an error from leaving the box stuck on. A
kill or death sets the outcome and drops a combat card into the Feed.

### Humanized actions

`humanize_action(name, args)` strips the MCP prefix, drops the JSON, and reads
the verb plus its one key argument (a direction, a target) into a phrase.
Unknown tools still read cleanly (verb plus first argument value). The mapping
is generic presentation, never game knowledge.

### Threading and safety

One exclusive worker per submission, cross-thread updates only as messages, the
parser and presenter mutate on the app thread. Esc sets a `threading.Event` the
agent checks at iteration boundaries. Cards render through `rich.text.Text`
with ANSI stripped at the presenter, so MUD prose is always safe.

## Verification

- The suite runs offline and hermetic: pinned config, stub transports, no key.
- The presenter is unit-tested without Textual: the humanizer, the de-noise
  boundary (plumbing events yield no card), room parsing, recent-action
  windowing, ANSI stripping.
- The presenter's combat detection is unit-tested on real fight text (room
  start without a description dump, blow-by-blow accumulation, kill to Victory,
  death to Defeat, a disconnect menu ending the fight without leaking), and the
  thinking behaviour (follows latest text, skips the placeholder, dedupes).
- Every interactive surface is driven headless with Pilot: splash open and
  dismiss, `/info`, tab switching, feed search, the combat box, the goal panel,
  the palette, a failing turn's error card.
- The real chain runs one scripted turn end to end and asserts the journey is
  you/action/thinking cards with no plumbing beats.
- Golden fixtures are verbatim real tbaMUD output, ANSI and CRLF intact.

## Done when

- `./11_tui` boots the splash card, then the live journey view against the real
  mud-manager, and the launcher's test run is green.
- `--replay` populates the Dashboard and Feed from the recorded real session
  with no key and no MUD.
- The raw technical trace appears nowhere in the TUI.
