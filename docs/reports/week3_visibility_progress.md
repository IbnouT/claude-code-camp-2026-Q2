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
- The audit that found the capability defects was therefore done by
  reading SQLite directly. That is the reason defects were missed until
  questioned.

## Plan review overturned three assumptions before any code was written

The plan was reviewed against the code. Corrections carried into it:

- Registering attempts in the shared registry would trip the
  one-live-character unique index and the session-directory guard, and
  would cause the contamination the plan forbids. Discovery is read-side
  only.
- There is no indexer. The sessions API recomputes per request, so
  verdicts need a cache or must be written by the runner into the
  ledger.
- The exploration simulator's substrate does not exist: the store holds
  no refusals, no door states, and no hazards, and its rooms are
  aliased. Replay runs from gateway journals instead, and policy sweeps
  are deferred behind the knowledge rework.
- `capabilities.perception` is rejected by validation in three packages
  and would be a sixth capability against a binding five-capability
  rule. That is a decision for Ibnou, recorded in the plan, and nothing
  in that track is built before it is answered.

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
