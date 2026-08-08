# Week 3 · The overnight run

Five units, in order. Each one lands on its own, reviewed before it
commits. The order puts the irreversible risk first and the visible
value second, so that stopping after any unit still leaves the tree
better than it started.

## Why this order

Committing first, because a day of work was sitting unrecorded and that
was the only thing here that could lose work. Then the Observatory,
which is unusable for minutes at a time while a session runs and so
blocks every kind of verification. Only then is it worth making the new
records visible, and only after that the register's remainder.

## Unit 1. Commit what exists

Done. Three commits on `week3/capable`, pushed:

- `935e15c` the gateway work, which had interleaved into one change
- `8ee9440` the Observatory believing a process rather than a row
- `04ddd39` one uv workspace

The gateway work was meant to be three commits and could no longer be
split: fifteen hours of it had accumulated in one tree, and the three
landings share forty one hunks across the same three files. The lesson
is the boundary, not the history. A landing is committed when it is
reviewed and green, before the next one starts.

## Unit 2. The Observatory stops wedging

Measured: `/investigation` costs 2.4s and returns 19.5 MB, uncached, and
the session view re-requests it every 2 seconds while a run is live.
Work arriving every 2.0s that takes 2.4s never drains, which is the
whole of it. Reproduced by driving that poll: `/api/health` goes from
0.0008s to 4.1s and recovers the moment it stops.

Four changes, in the order they pay:

- The live view stops polling the expensive endpoint. It polls something
  cheap that says whether anything changed, and fetches the whole story
  only when it has.
- The story stops carrying the entire conversation. `agent.jsonl` is
  quadratic, because every model request embeds the conversation so far:
  16.9 MB for 1154 records against 1.28 MB flat. Truncate before
  sanitising rather than sanitising and then truncating.
- Looking up one session stops scanning all of them. It opens 122
  databases and parses 122 agent logs to find one, twice per request.
  An indexed lookup already exists in the same file.
- Handlers that read files or databases move off the event loop, so one
  slow read cannot take the whole application down with it.

Judged by: `/investigation` under 300 ms on the largest recorded
session, and the app answering `/` while a live session is open.

## Unit 3. The quadratic toggle pattern

`TOGGLE_ENTRY` in `survival.py` has no anchor, so every position inside
a run of letters is a legal start and each one scans forward and
backtracks. Measured: 10 KB of letters 0.52s, 25 KB 3.24s, 50 KB 12.91s.
Four times the work for twice the input.

A real toggle reply is under a kilobyte and costs nothing, so this has
never been seen. It is a five minute fix and it removes a hang that only
needs one large reply to arrive.

Judged by: the same measurement, linear.

## Unit 4. The story shows the work nobody asked for

Every command now records who it was sent for: the agent when a tool
call it made produced one, the gateway when the gateway decided, and
`gateway-admin` on the immortal connection. Nothing reads it.

In one recorded session that is 193 immortal commands and 104 room
numbers, none of which appear anywhere in the Observatory. The agent
made 104 tool calls and the character issued 299 commands, so most of
what happened is invisible in the tool built to see it.

- Session records carry the issuer through to the API.
- The story shows gateway and immortal work in the same card shape as
  the rest, with a chip naming the issuer, so it can be told apart and
  counted.
- The room number appears where the room is identified.

The existing Sessions design is binding: the header, the view bar, the
story rhythm and the evidence drill-down already exist, and this plugs
into them with the tokens that are there. Anything needing a new visual
idea is a change of scope and needs saying so first.

Judged by: opening the session recorded tonight and seeing the immortal
traffic in its place, with the room number beside the room.

## Unit 5. What the register still holds

Only if the four above are done and reviewed. Take them in this order,
each its own commit:

- The standing rules reach the model in no run at all. The file is not
  copied into a measured attempt and both ways of failing to find it
  return the same silent empty string.
- Readiness thresholds are authored in no settings file, so most of the
  advice cannot fire and the one that does leaks its placeholder.
- `allow_raw` is honoured only when the gateway starts without a profile
  argument. With one, it and the enable and disable lists are all
  ignored.

## How each unit lands

1. Build it in full, wiring and consumers included.
2. Review it: give the reviewer the diff and the runtime question, never
   the prose. Ask for counterexamples rather than trust in the tests.
3. Fix everything the review finds, or take the disagreement back to it
   and reach agreement. Nothing is left unfixed by decision alone.
4. Run every suite. Never leave the tree red.
5. Commit with its tests, its README if touched, and its journal
   observation, then push.

Stop on: a suite that will not go green, a change needing a decision
that is not written here, or anything destructive. Never delete or
edit data that is evidence for a fix that has not yet been proven
against it.

## Commit messages

One concise sentence each, naming the change. No paragraphs. The detail
belongs in this plan, the journal and the code, which already carry it.
