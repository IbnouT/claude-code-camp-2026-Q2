# Live screen: evidence rail, combat, timeline, and agent messaging

## Goal

The Live map answers where the agent has been. This plan covers the rest of the
Live screen: what the agent is doing now, what state it is in, what it has
cost, whether it is making progress, and how an operator intervenes.

The map, header, navigation, `Ask about this session`, camera and map
toolbars, legend, thought dock title, and room inspector are built and are not
changed by this plan.

## Regions

| Region | Contents |
| --- | --- |
| Objective strip, under the header | The current objective and its clue |
| Map stage | Unchanged, plus a combat panel while an episode is active |
| Evidence rail, right | `NOW`, `CHARACTER`, `LIVE ECONOMICS`, `PROGRESS` |
| Causal timeline, bottom | Landmarks, cumulative cost curve, prefix transport |
| Header | `Message agent`, beside the unchanged `Ask` control |

## Rail blocks

## Objective strip

- The strip stays on one line. The clue truncates before the title, and the
  title truncates before the revision count.
- The title resolves from `objective_context.title`, then the compatibility
  `objective`. An exhausted fallback renders `No goal set`.
- A controllable session with no goal adds `First message starts the agent`.
- The optional clue is labelled as an objective clue. It is authored guidance,
  not current-world position evidence.
- A revision count above one remains legible only when `objective_initial`
  proves the ordinal. An operator replacement without a structured initial
  objective says `Goal replaced` without inventing a count. Source provenance
  stays in the evidence title.
- Historical inspection uses the objective valid at the selected prefix.
- Authenticated guidance does not replace the compatibility objective. Only an
  applied `revise` advances `objective_context`.

### NOW

- Posture from `player_status.fields.posture`. Active `combat` and
  `combat_episode` outrank a stale posture value.
- `LATEST TOOL ACTION` from `agent_belief`, with its age. `agent_belief` is
  the latest retained tool call rendered as a bounded phrase such as
  `Moving east` or `Attacking a large kobold`. It is not proof of a currently
  executing action, and it is never labelled as one.
- `LAST COMMAND`, derived from the retained timeline window.

### CHARACTER

- Bars for hit, mana, and move. Current values come from `vitals`, which is
  parsed from every numeric prompt. Maxima come from
  `player_status.fields.max_*`, which arrive only from `score`. Mixing the two
  sources makes current values appear stale after a score.
- Level and gold from `player_status`, which observes them only from `score`.
- Observed conditions: hungry, thirsty, drunk, poisoned. A chip renders only
  when the condition is observed true. Observed-false and absent conditions do
  not spend rail space.

### LIVE ECONOMICS

- Spend so far from `cost_usd`, against the cap. The cap bar respects
  `spend_cap_scope`: total cost against a session cap, current-turn cost
  against a turn cap.
- Cost per turn from `current_turn_cost_usd`, with a trend computed over the
  preceding window and the window stated.
- A sparkline over the last twenty entries of `economics`, labelled
  `cost per response`, because that series is per model response rather than
  per turn.
- Tokens in and out from `usage`, and cache hit as `usage.cache_read` over
  total input.
- Context fill as the latest `economics` entry's `context_tokens` over
  `context_limit`, labelled as the latest response and omitted when either
  source is absent.

### PROGRESS

The block remains in one stable position at the bottom of the rail.

- The fired state names `confusion_loop` or `progress_stall`, shows its retained
  evidence, and provides `Inspect attempts`.
- The measurements include:

  - new places observed over the last ten iterations
  - iterations since the last new place
  - repeated-command count for the current room when above one

When `confusion_loop` or `progress_stall` fires, the block turns amber and
names the rule above the same numbers. There is no separate empty state and the
block never disappears.

When lifecycle is paused, stopped, crashed, disconnected, or capture is
incomplete, the block states that condition in place of the numbers, because
the numbers would mislead. Active combat shows the numbers and notes combat.

## Combat panel

Rendered over the map only while `combat_episode.active`.

- Opponent and first observed turn from `combat_episode`.
- `outcome pending` while active. The `unresolved` outcome means capture ended
  with the episode open, which is a different and inactive state.
- No parsed combat lines. `LiveCombatLine` carries no actor, direction, or
  damage value, so the lines cannot be aggregated into a statement a viewer can
  act on.
- No health trend until the projection carries typed hit observations at
  episode start and now, each with provenance. A nearest-earlier observation is
  not health at the moment combat began.

The map keeps its mob badge. The badge answers where; the panel answers whom
and how long.

## Causal timeline

- Landmarks only: room changes from position items, level-ups from
  `milestones`, operator messages, friction, and combat boundaries.
- Room changes are the quiet baseline. Level-up, operator-message, and
  friction markers are emphasized and state their kind on hover and focus.
- A friction marker selects the last retained gateway sequence in the fired
  diagnostic's evidence. Its plain label is `repeated “command”` from
  `repeated_command`, or `no new place` for a progress stall. The diagnostic
  kind remains in hover and accessible text.
- An operator-control marker selects the first gateway sequence at or after
  its timestamp. That is the first prefix whose retained time includes the
  control event, not proof that the agent has applied it yet.
- Combat boundaries remain absent until the snapshot retains typed episode
  boundaries rather than one selected episode.
- The cumulative cost curve comes from `economics`, never from timeline item
  costs.
- Prefix transport: pause, step, and return to live. The API accepts
  `?through=` on the Live route and returns `through_sequence`,
  `latest_sequence`, `selected_at`, and `following_live`. Inspecting a prefix
  continues to learn the latest sequence without replacing the selection until
  the viewer returns to live.
- The retained timeline window holds the most recent items only, so the axis is
  labelled for the window it covers rather than the whole session.

## Message agent

- `Message agent` is a separate control from `Ask`. `Ask` is a read-only query
  over retained evidence; `Message agent` writes to a running agent. They never
  share a composer.
- Nudge maps to the `guide` action and Replace goal to `revise`. A revise
  replaces the objective, so the objective strip and the directive must agree.
- The composer states its target and the staleness of `expected_sequence`
  before sending, because an instruction written against a world state the
  agent has already left arrives at the next boundary reading as nonsense.
- Directives insert at the agent's next iteration boundary. They do not issue
  a MUD command directly.
- Operator message history requires the operator-exchange projection. Until it
  exists, agent activity following a directive is labelled as subsequent
  activity and is never presented as a reply.
- The start API accepts a player and a reset mode only, so an initial goal
  cannot be supplied from the launcher until that contract is extended.

## Delivery

- Phase 1: objective strip, `NOW`, `CHARACTER`, `LIVE ECONOMICS`, combat
  panel, `Message agent` control, thought dock age. No new projection.
- Phase 1b: `PROGRESS`, with the `confusion_loop` and `progress_stall` rules
  brought into the Live prefix at their existing thresholds and names.
- Phase 2: timeline transport with room and level-up landmarks and the cost
  curve.
- Phase 3: friction and combat landmarks, the operator-exchange projection,
  and typed health observations for the combat trend.

## Acceptance

- Every rendered value traces to a typed field. A value that cannot be sourced
  is absent, never substituted or inferred.
- Current health, mana, and move come from `vitals`; maxima come from
  `player_status`.
- An active combat panel never claims an outcome.
- The active-combat fixture keeps the panel in Focus occluder measurement and
  keeps the current room in the projected set.
- `PROGRESS` renders measurements in every state in which it renders numbers,
  and states the lifecycle condition otherwise.
- The cap bar matches `spend_cap_scope`.
- Locked surfaces are unchanged: header, navigation, `Ask`, camera and map
  toolbars, map, legend, thought dock title, room inspector.
