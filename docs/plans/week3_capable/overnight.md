# Week 3 · The overnight run

Five units, in order. Each one lands on its own, reviewed before it
commits. The order puts the irreversible risk first and the visible
value second, so that stopping after any unit still leaves the tree
better than it started.

## Why this order

A day of work sits uncommitted in one tree: five separate landings, none
of them recorded. That is the only thing here that can lose work, so it
goes first. After that the Observatory is unusable for minutes at a time
while a session runs, which blocks every kind of verification, so it
goes second. Only then is it worth making today's new records visible.

## Unit 1. Commit what exists, as five commits

Nothing is committed. Split by landing, not by file:

| Commit | Contents |
| --- | --- |
| 1 | The routine time bound: settings ceiling, `deadline_margin`, `_out_of_time`, stop-by-default dispatch, `needs_rest`, cancellation record, `tests/test_navigation_bounds.py`, `routine_bounds.md`, README, journal |
| 2 | Rooms keyed by the game's number: `observer.py`, the session hook, the projection change, `tests/test_observer.py`, the deletion of `identity.py` and the graph's identity machinery |
| 3 | The gateway cleanup: `truth.py`, `rules.py`, `rules.yaml`, `walk.py`, `progress.py` kept, `retract_layer`, the `derived` layer, `rules_file`, `record_room_numbers` |
| 4 | The Observatory believing a process rather than a row: the pid check, the fixture that carried the same mistake, two tests |
| 5 | One workspace: the root `pyproject.toml`, the path source becoming a member, one lockfile, the launchers, pytest aligned at 9.1.1 |

Approved messages are at the end of this document. Verify the suite is
green before each commit and never push.

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
   observation.

Stop on: a suite that will not go green, a change needing a decision
that is not written here, or anything destructive. Never push. Never
delete or edit data that is evidence for a fix that has not yet been
proven against it.

## The approved commit messages

```
Bound a routine to the call that carries it

A routine stopped after sixty steps, inside a call abandoned after
thirty seconds, and the two bounds had never been compared. Two of
three sweeps spent 237 of a run's 281 commands and reported nothing.

A routine now works back from the agent's own per-call timeout, read
from the settings entry that spawns this gateway, and stops a margin
early with an ordinary report. Routines no longer rest, since a rest
outlasts any call and recovery arrives on the game's tick. A routine
cut off despite the deadline records what it covered.

Stopping is now the default for any outcome a sweep does not
recognise. Reading an unknown outcome as carry on would spin without
awaiting, so nothing would yield and the call could not be cancelled.
```

```
Key rooms by the number the game gives them

Room identity was inferred from a candidate key of title, exits and
description, folded by a union-find until stable. It cost five hundred
lines and still left rooms duplicated and a map that did not join
across runs.

An immortal connection now joins each session as an invisible observer
and answers where the character is. That answer is the room's number,
so the same room carries the same subject in every run. Two rooms
sharing a title are separate without anything having to tell them
apart.

The observer asks only when the room can have changed, reads twice and
believes the answer only when both agree, and reconnects when a reset
takes its character. Nothing it learns reaches the agent.
```

```
Take out of the gateway what was never gateway work

Four modules had no caller and one had no business being there. The
authored rules were loaded and never read, a second copy of the file
the agent already reads. Observer truth was superseded by the observer
itself. A scripted walk was launcher work that had wandered in.

Removed with them: the layer identity computed into, the retraction
written for that layer, and two settings nothing read.

Kept: the progress reader, which is unwired rather than dead, and has
no substitute anywhere.
```

```
Believe the process, not the row

A run killed outright never writes its ending, so its row keeps saying
it runs. The Observatory read liveness from that column alone and
showed a session as live for two days after the process owning it had
gone.

Liveness now needs the row and the process. The fixture carried the
same mistake, asserting a session was live while recording no process
at all, so it was passing for the wrong reason.
```

```
One workspace, so no package runs a stale copy of another

The Observatory imports the gateway as a library and installed it as a
copy, so every session started from the Observatory ran gateway code
that had not been tested. Nothing signalled the difference.

The packages become one workspace on one lockfile. Members resolve
each other from source, so there is no copy to go stale. Aligning
pytest at 9.1.1 was required to resolve, and is worth having: three
versions were installed and a test could pass in one package and fail
in another for reasons nobody would see.
```
