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
