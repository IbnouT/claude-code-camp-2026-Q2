# Week 3 · Showing what actually happened

In one recorded run the model made 18 choices. The harness executed 281
game commands, injected 19 situation blocks, fired three reflexes, and
ran three mapping sweeps. The app shows the 18 choices, and shows two of
the sweeps as pure failures.

That is the problem. Work moved out of the model became invisible in the
tool built to watch it, and in two places the app does not merely omit,
it misleads.

Measured on `.boukensha/benchmarks/newbie_zone/attempts/20260807T162651Z`.

## What misleads, worst first

- Two sweeps show only `McpTimeoutError` after 30 seconds. Behind each,
  the routine kept walking: 149 and 88 commands, rooms still being
  mapped. A reader concludes the tooling is broken and the agent idle.
- The story is the model's tool calls, so 18 actions stand for 281
  commands. The map grows with no visible cause, and every look and
  exits call reads as the model's choice when it chose none of them.
- The block the agent is sent every turn appears nowhere, so the largest
  input to every decision cannot be inspected, and a bad decision caused
  by a wrong line in it cannot be traced.
- The prompt card says it shows the exact request, system prompt and
  messages. It shows neither the system prompt nor the block. A false
  label is worse than a missing one.
- Reflexes are invisible, so a reader watching health recover concludes
  the model chose to rest.
- Readiness is measured every iteration and shown nowhere, though it
  holds exactly the progress curve the mission is judged on.

## Nearly all of it is already recorded

Commands, routines, reflexes, readiness and identity are in the journal.
What is missing is that a command does not say who issued it, a routine
does not name the tool call it belongs to, and the block is only inside
the agent's own request record.

## The steps

1. Gateway: every command records who issued it, a routine records the
   tool call it serves, and a reflex records its trace. Attribution
   becomes a fact rather than an inference.
2. Gateway: the situation block is journalled as it was served, so what
   the model was told is observable independently of the agent's log.
3. Backend: records carry a typed issuer, routines adopt their parent,
   and reflex, routine, readiness and identity records reach the client.
4. Web: the story gains the harness's own voice. Sweeps read as "the
   navigator swept 12 rooms in 23 commands", expandable to every command
   and observation. Where the model saw a timeout and the routine kept
   walking, both are shown. Every step says whether the model chose it.
5. Web: the prompt shows what was actually sent, system prompt and
   situation block included, and the label stops claiming more.
6. Web: a per-iteration readiness strip, from data already recorded.
7. Live view gains the same distinctions, from the same components.

Steps 3 to 7 work on runs already recorded. Steps 1 and 2 make future
runs exact, so they come first.

## What must never be surfaced to the agent

The Observatory is for the operator, so room numbers and atlas truth may
appear there. Two boundaries stay hard: the journalled block records
exactly what was served and is never enriched, and nothing from the
observer layers may reach the block, the recall answers, or any surface
the agent reads.

## How each step is judged

By a person using the app on this recorded run, not by tests alone: the
281 commands are all reachable, the two timeout sweeps read truthfully,
and the block shown in the app matches the text in the agent's request.
