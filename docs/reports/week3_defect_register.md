# Week 3 · What the last batch actually did

Found by reviewing the unreviewed work against one recorded run
(`.boukensha/benchmarks/newbie_zone/attempts/20260807T162651Z`, 19 model
calls, 281 game commands) and against the game's own help file. Four
defects were found by hand first. Nine more were found by review.

## They are one chain, not a list

Brief mode empties room descriptions. Every arrival overwrites the text
a look had earned with nothing. Room identity keys on that text, so keys
flip on every step and same-titled rooms merge and unmerge. The map
stops growing. The sweep circles the same four rooms for twenty-six
moves. Three commands per step against a thirty second limit blows the
tool timeout. The routine is orphaned but keeps walking. Its rest reflex
sits the character down underneath the model, which then spends its last
five turns trying to move a resting character it cannot see is resting.

The run ended at level 1, no gold, no kills, stuck resting, with the
record claiming the auto-flee threshold had been set.

## Critical

- A sweep's step bound spans the time its call is given rather than
  sitting under it, so being cut off is the normal ending, and a cut-off
  sweep reports nothing. Sixty steps at three commands and 0.2s a
  command needs 36s against a 30s ceiling, and the measured sweeps ran
  at three commands a step. Two of three ended with no stop record and
  no result, having spent 237 of the run's 281 commands. The character
  is not left walking: the agent sends `notifications/cancelled` and the
  server library honours it, which is why both sweeps stop at the same
  instant. What is lost is the report, not control.
- The look meant to happen once happens on every arrival, because the
  arrival frame overwrites the stored description with an empty one
  before the check runs, and the other guard reads a field that does not
  exist. 89 looks for 96 moves.
- That same churn corrupts identity, which is what made the sweep
  circle. The identity module's own notes predicted it.
- `wimpy 13` is not a command in this game. The game answered "Huh!?!",
  the character played the whole run with no auto-flee, and the record
  says the threshold was applied.
- The standing rules reached the model in no configuration: the file is
  not copied into a measured run, and the capability is off by default.
  The run meant to measure the feature measured its absence, silently.
- Every number the advice depends on is authored in no settings file, so
  most of the advice cannot fire, and the one that does leaks its
  placeholder.

## High

- The block says "first time here" on the hundredth visit: it counts
  something other than visits.
- "Too dark to tell." is stored and shown as the name of the room
  beyond, when it is the game saying the way is unlit.
- The block omits posture, which is the one fact that would have
  explained the run's dead ending.
- Resting is not safe against cancellation: interrupted between rest and
  stand, the character stays seated forever.

## Moderate

- Four more pieces written where nothing reads them: the gateway rules
  module, its copy of the rules file, its settings entry, and the advice
  argument the caller passes empty. The same failure as the four before.
- One unreadable attempt registry takes down the whole session list,
  including the live player.
- The toggle table parser cannot match any multi-word switch name, and
  the ordering that keeps sacrificing safe is not enforced when a name
  fails to parse.
- Presence lines never expire, so something killed stays listed.

## What was sound

The read-before-set toggle protocol, verified live. The command
spellings for look, exits, rest and score. The block reaching the model
with its campaign line. The benchmark path fix. Observatory discovery
when registries are healthy.

## The lesson worth keeping

Every one of the four cheap per-arrival conveniences was defensible
alone. Together they took the map apart. Nothing in the tests could see
it, because each piece was tested in isolation with hand-built inputs,
and the pipeline that clobbers the data was never in the test.
