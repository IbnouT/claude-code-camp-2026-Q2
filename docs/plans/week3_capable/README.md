# Week 3 · Start here

Thirteen documents describe this week. Most are finished or superseded.
Read this one first and follow only what it points at.

## What is live

| Document | Read it for |
| --- | --- |
| `features.md` | The scope. F0 to F14, what each is judged by, and the dependency order. The single authority on what is in scope |
| `../../reports/week3_defect_register.md` | What one recorded run proved was broken. Fourteen items, marked critical, high and moderate |
| `../../reports/week3_visibility_progress.md` | What has been measured, including failures. Appended as work lands, never rewritten |
| `story_truth.md` | Six steps to make a run readable in the Observatory. None built |
| `overnight.md` | The current running order and how each unit lands |

## What is finished

These describe work that is built. Read them to understand a decision,
not to find work.

- `routine_bounds.md`, the time bound on a routine. Built and committed
- `gateway_cleanup.md`, what was taken out of the gateway. Done

## What is superseded

- `visibility_and_exploration.md` and `knowledge_rework.md` describe
  room identity as something inferred from title, exits and description,
  scored for merge precision. That is gone. A room is the number the
  game gives it, read by an observer, as `features.md` F1 sets out
- `perception_model.md` is a finished experiment, not pending work. Its
  honest state is in the progress report

## Where the work actually stands

Infrastructure is in reasonable shape. The mission is not: every
measured run still ends at level 1 with no kills and no gold. F10
combat, F12 the leveling loop, F13 equipment and economy and F14
verified plan conditions are unstarted, and they are what the mission
fails on. Room identity, the Observatory and the packaging move none of
it.

## The rules that govern the work

`../../../CLAUDE.md` holds the writing rules, the quality bar and the
build loop. Two that are broken most often:

- A landing is committed when it is reviewed and green, before the next
  one starts. Fifteen hours of work once accumulated in one tree and
  three separate landings could no longer be told apart
- Nothing is called done on one person's say-so. Every deliverable is
  reviewed by someone who did not write it, against the real data
