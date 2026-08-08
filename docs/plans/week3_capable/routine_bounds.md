# Week 3 · Bounding a routine to the call that carries it

The design for the first part of F6 in `features.md`. A routine is
bounded in steps, the call carrying it is bounded in seconds, and the two
have never been reconciled, so a sweep with ground to cover is cut off
and says nothing. This describes what changes, what it breaks, and how a
person sees for themselves that it worked.

## The shape of it

```
 settings.yaml
   mcp_servers.mud.timeout: 30      read by the agent as its call ceiling
                                    read by the gateway to derive from
   capabilities.navigation.deadline_margin: 4

           deadline = ceiling - margin = 26s
                │
   sweep starts │
     ├─ step ───┤ every step asks the clock before it walks
     ├─ step ───┤
     ├─ step ───┤ at 26s the next step is not taken
     │          │
     └─ report ─┘ stop reason "time_limit", the usual five counts
                │
                └─ 4s of headroom left for the slowest possible step
                   already in flight, plus the record and the reply
```

## The numbers, and where each comes from

Measured on the newbie-zone attempt of 7 August, over the 255 command
gaps that fall inside a routine, with the rest loop excluded. Gaps
outside a routine are not evidence about a routine's pace. Decomposed,
the long ones are all waiting rather than working: the longest is a turn
boundary carrying the model's own latency, and the next is the pause
while the character is reset, which ends with the game announcing the
arrival. The command that follows that pause was answered in 0.05s.

| Quantity | Value | Source |
| --- | ---: | --- |
| command inside a routine, median | 0.200s | the run |
| command inside a routine, 95th | 0.205s | the run |
| command inside a routine, slowest | 0.303s | the run |
| worst step, four commands | 1.21s | the slowest, four times |
| margin, default | 4.0s | the worst step, and a safety factor of about three |
| ceiling | 30.0s | `mcp_servers.mud.timeout` |
| deadline | 26.0s | ceiling less margin |

A step is up to four commands, not three. It stands the character first
when it is seated, which the model can cause by resting between calls
and combat can cause mid-sweep, and only then moves, reads and asks.

Only part of the margin is measured, and the design says which part. The
worst step observed inside a routine is 1.21s. The rest is an authored
safety factor of about three, and it is authored because the run gives
it nothing to be derived from: once every long gap is decomposed, no
command anywhere in the run took longer than 0.303s. The factor is
insurance against what one run on a quiet local game cannot show, game
ticks, saves under load, and a network that is not a loopback. It is not
sized to cover the worst imaginable pause, because a margin that wide
would spend most of every call doing nothing. Anything past it is what
the cancellation path exists to catch, and that path now leaves a
record.

## What changes, file by file

`mud_gateway/settings.py`

- Read the ceiling from the document already parsed, and expose it. The
  narrowing to the `gateway` key happens after the whole file is loaded,
  so nothing new is opened.
- The gateway's own entry under `mcp_servers` is the one whose `command`
  is `boukensha-gateway`, which is how the agent already recognises it.
  Matching the key name instead would read another server's ceiling
  whenever the entry is renamed, and read it silently.
- A navigation capability with no ceiling in the file is a configuration
  error, named and refused, not a guessed thirty.

`mud_gateway/navigation/executor.py`

- The executor takes a clock and a deadline. The clock is injected so a
  test can move time without sleeping.
- The check lives inside `_step`, which is the one place every walked
  step passes through. Put anywhere else it has to be repeated at each
  call site, and the executor has four of them: the route walk, the
  frontier step after a walk, the live-frontier step when the map knows
  no frontier, and travel's own walk. Two of those have no check today.
- A step that finds the deadline passed returns without walking, so no
  caller can step past it by having been written before the check.
- Sweep's handling of a step's outcome becomes exhaustive. Today each of
  its three dispatch sites lists the outcomes that stop and lets an
  unlisted one fall through to the next loop. A new reason therefore has
  to be remembered in three places, and forgetting it in one does not
  stop the sweep.
- Stopping becomes the default instead. Only `moved` and `walked` carry
  on, `blocked_exit` and `unexpected_room` are the named setbacks, and
  every other outcome reports and returns.
- A new stop reason, `time_limit`, joins the existing set and reports the
  same five counts as any other stop.
- `_step` no longer rests. When movement falls below the floor it returns
  `needs_rest` and the routine stops with that reason.

`mud_gateway/survival.py`

- `recover_movement` keeps its behaviour and loses its only caller. It
  stays because resting is still the right thing between calls, where
  there is time for it.

`.boukensha/settings.yaml`

- `timeout: 30` becomes a real key rather than the commented line it is
  today, so the derivation has a number to read and every attempt
  inherits it.

## Why an unhandled outcome would hang rather than misbehave

The exhaustive dispatch is not tidiness. A step that refuses on the
deadline returns without awaiting anything, so a loop that treats the
refusal as "carry on" spins with no await in it at all. Nothing yields
to the event loop, so the connection is never read, and the cancellation
that would otherwise cut the call cannot even be delivered. A single
missing entry in one dispatch list would turn a sweep into a gateway
that has to be killed, which is worse than the defect being repaired.

Stop-by-default removes the possibility rather than relying on three
lists being kept in step.

## Why the routine stops rather than resting

A rest cannot fit and would not help if it did. The full loop is twenty
polls of six seconds, so 120s against a 30s ceiling, and movement returns
on the game's own tick: the one rest in the record recovered nothing at
all across 12.6s of sitting. Truncating it to fit would sit the character
down, gain nothing, and hand back a character that cannot walk.

The model already has the means. `set_position` offers `rest` among its
choices and the run shows the model using it, so stopping with
`needs_rest` returns the decision to the one place that has time to act
on it. Nothing new is built for recovery.

This is also what removes the posture problem at its root. The routine
never sits the character down, so no cancellation can leave it seated by
the routine's doing. The alternative, standing the character back up
after the cancel has landed, cannot be done honestly: once the scope is
cancelled every await raises at once, and a shield that reached the game
anyway would be a network round trip running inside a cut that is meant
to have ended.

## The cancellation path

The deadline is what makes cancellation rare, not impossible. A slow game
can still overrun, so the path is written for it:

- The routine catches the cancellation, writes its stop record with the
  ground it covered, and re-raises. Nothing swallows it.
- The record is written with a synchronous SQLite append and no await
  between catching and re-raising, so that path cannot itself be
  cancelled halfway.
- The stop reason is `cancelled`, so a reader can tell an overrun from a
  clean deadline stop and know the two apart in the record.
- No result reaches the model on that path. The library answers the call
  with its own cancellation error, which is why the record exists for the
  person reading the run rather than for the model.

## What this breaks

- A sweep that would previously rest and carry on now stops. Runs where
  movement runs low will show more, shorter routine calls, and the model
  is expected to rest between them.
- Any test asserting the old resting-inside-a-step behaviour changes with
  it. `test_survival.py`'s direct tests of `recover_movement` stand,
  since the method is unchanged.
- A navigation capability enabled with no ceiling in the settings file
  now refuses instead of running. That is the intended failure, and it
  reaches the model as a typed `capability_unavailable` result on the
  call itself. The refusal is decided from settings before anything
  connects, so it never costs a login first and never arrives under some
  other name.
- A margin that is not greater than zero and smaller than the ceiling
  refuses the same way. Stating what a usable margin is, rather than the
  one way it was seen to fail, is what makes the check hold: a negative
  margin puts the deadline past the ceiling and brings the silent
  overrun back, and a margin that is not a number at all never compares
  true, so the deadline would never fire.
- Two settings entries that both spawn this gateway and state different
  ceilings are refused. A running gateway cannot tell which one started
  it, so taking either would make the bound depend on file order.
- Nothing changes with the capability off. The clock is only consulted
  inside routines.

## Ordering against the look-once fix

The look that should happen once per room still happens on nearly every
arrival, which is what made the measured steps cost three commands rather
than two. Fixing that lowers a step to about 0.4s and lets far more
ground fit inside the same deadline.

The two fixes are independent and this one does not wait. The margin is
derived from the four-command worst case, so it stays correct while
steps are expensive and stays correct, with room to spare, once they are
cheap.

## How a person verifies it

From a run's journal, without reading any code:

- Every `routine_start` has a `routine_stop` sharing its trace id. In the
  attempt this design comes from, two of three did not.
- Every sweep `tool_call` has a `tool_result`. Two of three did not.
- No routine's commands span more than the ceiling.
- No routine leaves the character seated. A run can still end seated
  because the model rested and stopped there, which is its decision to
  make, so the record to read is the posture when a routine stops.

In the Observatory, a sweep that stopped on its deadline reads as an
ordinary stop with its counts, in the same shape as a sweep that ran out
of frontier. A stop reason of `cancelled` is the signal that a call
overran, and it should be absent from a healthy run.

## The tests, by name

- a sweep stops on its deadline and reports the ground it covered
- a route walk checks the deadline between its own steps
- the frontier step after a route walk is checked, which is the step that
  walks past the deadline today
- the live-frontier step is checked, which is the other one
- a step offered exactly at the deadline is not taken
- a sweep begun seated pays four commands for its first step and the
  margin still holds
- a step that finds movement low stops with `needs_rest` and does not rest
- a cancelled routine writes its stop record and re-raises
- a cut landing in the first step, before any ground is covered, still
  writes a stop record
- a cut mid-reply leaves the session able to parse the next command
- a step refusing on the deadline ends the routine with a report from
  each of sweep's dispatch sites, not only the first
- an outcome sweep has never seen stops it, rather than being carried
  past by a dispatch list that does not name it
- navigation with no ceiling in the settings refuses and names the key
- the refusal reaches the caller as `capability_unavailable`
- the ceiling is read from the entry whose command is the gateway, not
  from a key named by convention
- travel is bounded by the same deadline as a sweep
- the deadline is the ceiling less the margin, from settings

Every one of them runs without a MUD and without a model, on the existing
fakes, with an injected clock so no test sleeps.
