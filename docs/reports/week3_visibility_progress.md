# Week 3 · Visibility and exploration progress

Appended as each step lands or fails, with the numbers and the runs they
came from. Failures are recorded as plainly as passes.

## Room identity is broken, and it invalidates a reported result

Measured on `.boukensha/profiles/poucet/knowledge.db`:

| Measure | Value |
| --- | ---: |
| place ids | 478 |
| distinct room titles | 114 |
| exit links | 588 |
| links crossing a session | 0 |

Place ids are minted per session, so the same room becomes a new place
in every run. "Main Street" exists 34 times under 34 ids.

What this overturns: the capability report's warm-map figure of 235
rooms accumulated across five runs counted place ids, not rooms. Those
runs produced five disconnected partial copies of a small neighbourhood.
The map does not accumulate across sessions, and no coverage measure,
re-tread rate, or travel-by-title is well defined until identity is.

## The Observatory cannot see any measured experiment

- The main registry holds 71 sessions. Benchmark attempts run under
  their own `BOUKENSHA_DIR`, each a complete runtime layout with its own
  registry, and the Observatory reads only the main root.
- 20 suites, including 16 minotaur attempts and 12 capability-batch
  attempts, are invisible in the app built to inspect runs.
- Capability defects were therefore found by reading SQLite directly
  rather than by using the app, which is why several were missed.

## Constraints the plan must respect, measured

- Registering attempts in the shared registry trips the
  one-live-character unique index and the session-directory guard, and
  causes the contamination the plan forbids. Discovery is read-side
  only.
- There is no indexer. The sessions API recomputes per request, so
  verdicts are written by the runner into the ledger.
- The exploration simulator's substrate does not exist: the store holds
  no refusals, no door states, and no hazards, and its rooms are
  aliased. Replay runs from gateway journals instead.
- `capabilities.perception` is rejected by validation in three packages
  and would be a sixth capability against a binding five-capability
  rule. That is a decision for Ibnou, recorded in the plan.

## The first identity rule failed against its own data

- An absolute "same-session aliases never merge" rule is refuted by the
  store: Temple Square holds two aliases in one session and Market
  Square three, minted when the position tracker loses confidence. The
  rule would split the hub rooms every route crosses, leaving Temple
  Square as 12 rooms and Main Street as 13.
- The advertised fold of 478 aliases to 265 rooms is not reproducible.
  Two faithful readings produced 348 and 288, because with no
  cross-session links, agreement between two aliases is only definable
  through the identity relation itself. Identity is a fixpoint and the
  first draft never said so.
- Consequence for this plan: identity criteria are predicates, and the
  measurement script lands with the step.

## Perception experiment, final honest state

- Reproducible artifact: 12 of 16 labels meet their floors, trained on
  observed play plus authored text, tested on 400 real blocks never
  trained on.
- The 15-of-16 result is unreproducible: its corpus pool was appended to
  and its artifact overwritten. Recorded as a reproducibility failure.
- All per-label numbers are optimistic. The frozen set was consulted
  after every round and the data and protocol were changed to move it,
  roughly twenty times. An honest number requires fresh reviewed text,
  which is what shadow mode is for.

## F0 landed, F1 rule approved after four reviews

- F0, the wiring repairs: envelope unwrap, posture check before walking, and
  the withdrawal of the required response line. Committed. The envelope fix
  and the posture fix were each watched working against the live game.
- F1's identity rule: approved on the fourth review. Merge precision against
  the game's own room numbers is 100 percent over 502 merged pairs, against
  94.3 percent for the first rule written and 70.1 percent for matching on
  title. It joins 43 percent of the pairs that are truly one room.
- Four reviews, four defects, none of which the tests written beforehand could
  see: a rule that merged five different maze rooms, a difference test that
  read "not yet proven same" as "proven different", a block that checked one
  side of a merge, and a difference relation that stopped one hop short.
- Recorded as known limitations rather than hidden: room descriptions carry
  what was happening in the room, which falsely proves 27 pairs different and
  blocks 188 correct merges, and difference is proven between places rather
  than between the rooms they were merged into.
- The derived layer, its retraction path, and the map reading joined rooms are
  landed. Recording identity also exposed a store defect: a fact re-asserted
  after retraction attached evidence to the withdrawn assertion and never came
  back, so the store looked as if it had recorded an observation while the
  fact stayed absent. That is the likely cause of the empty map after a
  knowledge reset.


## F1 wiring landed, with one part blocked

- The map now joins during play, not only after a run ends. The review
  found the earlier wiring correct and useless: every room entered in a
  run belongs to no joined room until the run ends, so the agent always
  stood somewhere the joined map did not contain, and travel to a room
  known from a previous run returned unreachable every time.
- Two store defects found by the same review and now tested: withdrawing
  facts emitted no change records, so a reader following the feed would
  show vanished facts indefinitely, and re-observing a withdrawn value
  attached evidence to the withdrawn claim rather than contesting what
  had become current.
- Blocked and recorded rather than forced: recording the game's own room
  numbers needs a channel that does not cross the boundary keeping
  immortal code out of the agent's runtime, which is enforced by a test.
  Two designs are written in the plan for Ibnou to choose.
- F1 cannot be measured against baseline until a mission runs with the
  knowledge capability on. That measurement is outstanding.

## F3 started: the description was recording the moment, not the place

- A room's description absorbed every line the parser could not classify,
  including creatures, floor items and combat messages, so the same room
  read differently on different visits. It now ends at the exits line.
- Measured cost of the defect on the existing store: 27 pairs falsely
  proven different, 188 correct merges blocked. The fix changes future
  runs only. Repairing the recorded past needs journal replay.

## A routine now stops before its call is abandoned

- The measured defect: of three sweeps in the newbie-zone attempt, one
  reported and two were cut at 29.85s having issued 149 and 88 commands,
  leaving no stop record and no result. 237 of the run's 281 commands
  reported nothing.
- Cancellation was never the problem. The agent sends it and the library
  honours it, which is why both sweeps stop at the same instant. The
  report is what was lost.
- Three measurements of command cost were wrong the same way before one
  was right. An event-to-event gap holds whatever was waiting: a turn
  boundary, a reset pause, a rest. The margin was first built on a 1.995s
  "command" that was setup work, a `score` two seconds after a reset
  pause had ended. Inside a routine the slowest gap is 0.303s, and at the
  wire the slowest command in the run is 0.114s.
- The margin is therefore stated in two parts: a measured worst step of
  1.21s, four commands because a step stands the character first, and an
  authored factor of about three that the run cannot justify.
- Resting moved out of routines entirely. The loop sleeps up to 120s
  against a 30s call, the one rest on record recovered nothing in 12.6s,
  and the cut landed between sitting down and standing up, which is how
  the run ended seated.
- Found only by asking what a missed case would do: the sweep listed the
  outcomes that stop and let others fall through, and a step refused on
  the deadline returns without awaiting. One missed entry would spin
  without yielding, so the connection would never be read and the call
  could not even be cancelled. A hang, not a wrong answer.
- Proven by reverting the dispatch and running the new tests: the suite
  hung rather than failing, and the timeout wrapped around the test could
  not fire either. Two tests written first had passed against the
  reverted code, because both reached the one dispatch site already
  correct. The tests now cap refusals and fail with a sentence.
- Live verification without a model, since no API key is configured:
  three sweeps against the running game pair start to stop with none past
  the ceiling, and with the deadline moved deliberately close all three
  stop on it and report.
- A negative margin passed the first guard and put the deadline past the
  ceiling, which is this defect returning through a one-character typo.
  The guard was written as the way the bound had been seen to fail rather
  than as what a usable bound is. Stated as a range it refuses negative,
  zero, and a value that is not a number, all of which leave the deadline
  unable to fire.
- Outstanding, not skipped: the configuration unit has no measurement
  against baseline. That needs the same journey run with the capability
  off and on, which needs model calls, and an attempt dies at the first
  one with a 401 because no API key is configured. Nothing here claims a
  measured effect on the mission.

## Open defects and missing pieces, as of the newbie-zone run

Found by hand during one live run, not by tests. Recorded here so the
work survives whatever comes next.

### What the agent is shown

- The room's own text now reaches the agent nowhere. Brief mode was
  turned on and the look that reads a room is issued by the harness, so
  the text is parsed into facts and dropped. Before, the agent saw a
  description on every move. The intent is the opposite of what landed:
  the description belongs in the first arrival and nowhere else.
- The look meant to happen once per room happens on nearly every
  arrival: 89 looks against 96 moves over 17 rooms in the recorded run.
  Whatever the check asks, it is not "do I already hold this room's
  text".
- An exits listing entry of "Too dark to tell." is stored as the name of
  the room beyond. It is not a name, it is the game saying the way is
  unlit, which is the darkness signal the contract wants.
- An exit can name the room it leaves from, which is either a loop or
  two rooms sharing a name, and is shown as though it were neither.

### What the Observatory does not show

- The standing block is sent as its own message beside the tool result
  and appears nowhere in the session view, so what the agent is actually
  told can only be read out of a log file. Every claim about it is
  therefore unverifiable by the person reading the app.
- Commands the harness issues on its own, which in the recorded run were
  89 looks, 83 exits, the toggles, wimpy and rest, are absent from the
  story. The story shows the 19 model calls and hides the work that did
  most of the walking. Moving work out of the model made that work
  invisible in the tool built to see it.
- Sessions need a section of their own for harness-issued steps, marked
  as the harness acting rather than the model deciding, so a reader can
  tell them apart and count them.

### What has and has not been reviewed

- Reviewed: the wiring repairs, room identity, the facts work, recall.
- Not reviewed: the authored rules, readiness advice, the state block
  rewrite, exit destinations, the game toggles, look-once, standing
  advice in the system prompt, the Observatory multi-root discovery,
  and the benchmark path fix. Four defects were found in that batch by
  hand within an hour, so the rest of it should be assumed to hold more
  until a review says otherwise.

## The Observatory wedges because the live view polls its most expensive read

Measured and reproduced, and long-standing rather than new.

- `/api/sessions/{id}/investigation` costs 2.4s of CPU and returns
  19.5 MB, uncached. The session view re-requests it every 2 seconds
  while a run is live. Work arriving every 2.0s that takes 2.4s never
  drains, which is the whole of the hang.
- Reproduced by driving that poll alone: `/api/health` goes from
  0.0008s to 4.1s and recovers the instant polling stops.
- Every handler is `async def` with its work inline, so one slow read
  blocks the event loop and the app stops answering anything at all.
- 1.5s of the 1.7s projection is redaction: 1.75 million regex calls by
  volume, not backtracking. The patterns themselves are linear at
  66 MB/s and are not worth changing.
- It worsens over a run because `agent.jsonl` is quadratic: every model
  request embeds the conversation so far, so 1154 records are 16.9 MB
  against 1.28 MB flat.
- Looking up one session linearly scans all 122, opening each database
  and parsing each agent log, twice per request. An indexed lookup
  already exists in the same file and is unused.
- Nothing caches anywhere. Three identical calls: 2.52s, 2.10s, 2.56s.

Ruled out: the room number work, the issuer field and the new event
kinds. No Observatory code references any of them.

## The state block reaches the model in no run

Measured on session `6df1300b`, at the level of what was actually sent:
0 state blocks across 144 model requests.

- The block would appear in `agent.jsonl` as a user message beginning
  `[state]`, inside each request's `messages`. The log records the full
  `messages` and `system`, so its absence is the block's absence, not a
  gap in the record.
- It has no source. `run_dsl.py:351` yields one only when the knowledge
  capability is on and a `recall_state` tool is registered. That run
  offered 25 tools, all `tbamud__*`, and none of them was `recall_state`.
- The system prompt that did go out is 1343 characters of generic
  advice, naming no standing rule.

So the agent played 144 model calls with no knowledge state and no
authored rules. Every claim about what the rules do to behaviour is
untested, because the rules have never been in front of the model.

## The Observatory answers while a session runs, and a target that cost more than it bought

Measured on session `6df1300b`, the largest recorded, through the
running app.

| Measure | Before | After |
| --- | ---: | ---: |
| `/investigation` | 2.4 s, 19.3 MB | 0.535 s, 3.57 MB |
| Fetched | every 2.0 s | only when the session changed |
| `_agent_fields`, sanitised and returned | 0.601 s | 0.014 s |
| One session lookup, paid three times | 1.04 s | ~0.01 s |
| `/api/health` under that poll | 4.1 s | ~0.3 ms |

What fixed it was not making the answer smaller. It was not asking: the
view polls a 5 ms change signal and fetches the story only when it
moves.

Two designs were built or drafted to make the response smaller, and both
were withdrawn on measurement.

- A record window returning the most recent 200 of 4845 records reached
  210 ms and 0.29 MB. It also opened the story at Turn 2 with its first
  iteration numbered 122, and every heading counting iterations counted
  the loaded ones, reporting 11 against 143. Review then found its
  boundary rule failing on real data: 1314 records carry no iteration
  scope and sort inside one, so 362 of 1180 window sizes cut
  mid-iteration and displayed $0.000000 against $0.000325 actual.
- An outline of every turn and iteration, always whole, with contents
  loading forwards. Rejected before it was built: every figure the
  outline carries is an aggregate over the records it replaces, so it is
  0.0008 s of the 0.370 s projection and each contents request pays that
  projection again. It multiplies server work to save transfer.

The 300 ms target both served was written into the plan by the person
doing the work and never put to anyone. Recorded because the defect it
produced was not slowness, it was a story that no longer began at its
beginning, and it survived two review gates before a person opened the
page.

## A quadratic pattern that has never been seen

`TOGGLE_ENTRY` in `survival.py` is unanchored, so every position inside
a run of letters is a legal start and each scans forward and backtracks.
Measured: 10 KB 0.52s, 25 KB 3.24s, 50 KB 12.91s. A real toggle reply is
under a kilobyte and costs nothing, which is why it has never fired. It
needs one large reply to become a hang.

## Where the mission stands, against all of this

Every measured run still ends at level 1 with no kills and no gold.
Room identity, the Observatory and the workspace are infrastructure and
move none of that. F10 combat, F12 the leveling loop, F13 equipment and
economy, and F14 verified plan conditions are unstarted, and they are
what the mission fails on.
