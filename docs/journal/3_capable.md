# Week 3 Technical Documentation

## Technical Goal

Make the agent capable of a hard game goal on a small model: find and kill
the Massive Minotaur, a strong monster somewhere in the unexplored game
world, efficiently in steps and cost. Week 2 made the agent observable.
Week 3 uses that instrument to find out why missions fail and to build the
knowledge and machinery that make them succeed.

The design premise, argued before any evidence: a hard goal handed to a
fresh model is a failure before the mission starts. The game has survival
rules a language model cannot know from the goal text alone. Characters
tire after too many moves and must rest. Dark areas blind the player
without a light source. Some monsters attack on sight. Health, hunger,
thirst, equipment, and experience level all gate what is survivable. The
plan is therefore knowledge first: facts the agent earns by playing, rules
we author for it, and deterministic machinery (route planning, survival
reflexes, a preparation planner) that spends the model's attention only on
judgment. The full design is in
[the knowledge plan](../plans/week3_capable/knowledge.md).

## Technical Uncertainty

- I do not know whether a small model can complete this mission at all,
  even with good knowledge. The binding constraint could be model judgment
  rather than missing facts.
- I do not know which failure actually dominates: not knowing where the
  target is, dying to game mechanics, or burning the budget on wandering.
  Guessing wrong would spend the week building the wrong capability first.
- Moving decisions out of the model and into deterministic code risks
  hiding failures instead of fixing them, if the machinery is wrong.

## Technical Hypotheses

- Repeated identical attempts will fail in a stable, measurable pattern,
  and that pattern will rank the capabilities to build better than any
  design argument.
- Most of the budget will be lost to navigation and wandering, not to
  wrong decisions at genuine choice points.
- Survival mechanics (exhaustion, darkness, aggressive monsters, hunger)
  will fire inside even short runs, without the agent understanding them.
- Knowledge retained across runs will make repeat missions measurably
  cheaper, which is the claim the week should end by proving or refuting.

## Technical Observations

### 1. Thirteen cold missions, zero sightings: the autopsy ranked the work

Before building anything we ran the mission as-is, repeatedly, to let
recorded failures choose the build order. Method: the benchmark launches
the unmodified agent with the goal "Find the minotaur and kill it.", no
location hint, on the small model already in use. Every attempt is cold:
the player is reset to the temple at level 1 with baseline memory, and a
verified reset receipt is retained before the first model call. Each
attempt is capped at eight minutes of wall clock and about twenty cents of
model spend. Success is judged only from game evidence (the monster's
death message), never from the agent's own claim.

Thirteen attempts completed, costing $2.84 in total.

- No attempt ever saw the minotaur. Roughly 1,150 model calls produced
  zero sightings of the target. Every attempt spent its entire budget
  wandering, which confirms that locating the goal is its own problem, not
  a detail of movement.
- Darkness was the dominant hazard by an order of magnitude: 79 retained
  "it is pitch black" observations. The agent walks into dark areas it
  cannot perceive, keeps acting blindly inside them, and does not leave.
  In the design's failure inventory darkness was one hazard among many.
  The evidence promoted it to second place.
- Aggressive monsters attacked 12 times and killed the agent 3 times.
  The agent fled 4 times, so escape happens, but not by policy.
- Movement exhaustion rejected commands 6 times, and hunger and thirst
  appeared even within eight-minute runs.
- Attempt cost was stable near the ceiling (about $0.22, roughly 90 model
  calls) with two shorter self-ended runs, so the failure pattern is
  consistent rather than noisy.

One methodological result stands on its own: the observability stack paid
for itself here. A live map defect surfaced during the first manual
mission (the layout crashed on a world shape only deep exploration
produces), was reproduced from the retained session payload, fixed, and
pinned by a regression test, all while the mission kept running.

The consequence for the plan: build the locate machinery first, darkness
handling second, then the rest and flee reflexes. Combat interrupts
matter, but nothing else matters while every dollar goes to blind
wandering.

### 2. The capabilities landed as five flags, and the first live sweep paid off

The build followed the autopsy's ranking as five independently switchable
capabilities: navigation (routing and systematic exploration over the
agent's own map), knowledge (a re-rendered state summary each model call,
required per-response state fields, and the agent's assertions stored as
distinct beliefs), survival (numeric reflexes: the game's own auto-flee
threshold kept set, rest before movement runs out), economy (banking gold
above a ceiling at a place the agent recorded as a bank), and campaign
(a deterministic mission phase chosen from typed readiness). With every
flag off, the advertised tool surface and its digest are unchanged from
the measured baseline, so any subset can run as an experiment arm.

The one live verification that fit before the account's API credits ran
out was worth the night on its own: a single exploration call walked 47
steps and discovered 30 rooms with typed stop reasons and vitals
tracking, where the baseline had spent roughly 90 model calls per attempt
discovering less. The same short verification loop caught two defects no
unit test had found, because both lived in real data:

- Stored exit lists use the game's abbreviations ("n") while learned
  exit links use full words ("north"), so the set arithmetic that finds
  unexplored exits never matched on real stores. The synthetic test
  fixtures had used full words on both sides and hidden it.
- Right after a baseline reset, the store is wiped but the in-process
  position state is not, so the two disagree about the current room at
  exactly the moment a cold mission starts. The exploration routine now
  falls back to the live room observation; whether a reset should also
  reset in-process state is an open question.

Credits ran out mid-verification, so the comparison batch, the
per-capability measurements, and the learning curve remain queued rather
than claimed. Nothing in this observation asserts mission improvement:
that number does not exist until the batch runs.

### 3. The before and after: fewer decisions, no deaths, a map that compounds

With credits restored, the same mission ran as three measured cohorts
against the retained thirteen-attempt baseline, all under the same reset
and the same evidence-based judge.

- Cold, all capabilities on, eleven attempts: 28.5 model calls per
  attempt against the baseline's 86.3, a 67% reduction, and the spread
  collapsed from ±21.4 calls to ±0.5. Deterministic routines made
  attempts nearly identical where the baseline was noise. Zero deaths
  against three, and none of the baseline's hazard signatures (79
  darkness lines, 12 attacks, 6 exhaustion rejections) appeared at all.
  Two caveats stated: the per-attempt cost ceilings differed slightly,
  and bounded sweeps may avoid hazards partly by staying nearer safe
  ground.
- The tool mix explains the reduction: a capable attempt issues sweep
  routines and reads its state summary, with zero single-step move
  calls. The model spends its calls deciding, not walking.
- Warm, knowledge retained across five runs: call counts stay flat at
  the spend ceiling, but coverage compounds. The persistent map grew to
  235 distinct rooms where a cold attempt maps about 35, and every run
  pushed into new ground.
- The minotaur was never sighted in any cohort. The world is larger
  than the explored radius under these budgets, so the mission itself
  remains open. The honest claim is efficiency, survival, and compound
  coverage, not victory.

### 4. Reading the transcripts overturned the night's story

The batch numbers were reported before any transcript was read. Opening
one attempt's full log, message by message, changed the account.

- The mission-phase line the model received on every call was broken: a
  wiring fault fed it the wrong JSON layer, so every readiness field read
  "None" and the line always said "sweep them". The phase machinery's
  entire runtime effect was a constant instruction to explore.
- The required end-of-response state line was ignored on 27 of 27
  iterations even though the contract was verifiably in the prompt. The
  cause is structural: responses that call tools carry little or no
  text, so demanding a text line on every response fights the tool
  mechanism itself. The idea needs a different carrier, not a retry.
- A sweep died after four steps because the character was resting and
  the game refused to move it ("You feel too relaxed to do that"). The
  routine never checks posture before walking. Two earlier explanations
  for this stop were wrong until the journal was read.
- The model's own thoughts are 27 near-identical repetitions of
  "continue sweeping to find the minotaur". Nothing it ever saw
  mentioned its level, equipment, skills, or gold, so no other thought
  was possible.

The deeper findings are about the knowledge design itself. The store
holds only the structural skeleton of what the parser sees: room names,
exits, connections, creature and object names, own vitals. Everything
qualitative stays in the raw logs and never becomes knowledge: what
shops sell, what signs say, darkness, appraisals of monsters, doors and
keys. And the model has no way to read even the stored part: its only
window is a four-line count summary. Exploration reports pure geometry,
so the model cannot steer toward promising areas or notice a shop, a
corpse, or the target itself passing by. A swept-past minotaur would
have been recorded silently and never announced. The week 0 play skill,
with a plain text memory read before every action and a page of common
sense rules, understood the game better than this machinery does.

The call-count collapse from observation 3 stands as measured, but its
meaning shrinks: it measures cheap walking, not competent play. The
capability that matters, playing the game, was not built: no readiness
against a target, no preparation, no economy loop reached, no strategy.

## Technical Conclusions

- Repeated identical attempts did fail in a stable pattern, and that
  pattern ranked the build order better than argument: confirmed.
- Most of the budget was lost to navigation, not decisions: confirmed,
  and moving navigation into deterministic routines removed two thirds
  of all model calls.
- Survival mechanics fired inside short runs without the agent
  understanding them: confirmed at baseline, and the reflex layer plus
  bounded routines reduced observed hazard events to zero in the
  measured cohorts, with the safer-ground caveat retained.
- Knowledge retained across runs makes repeat missions cheaper:
  partially confirmed. Coverage compounds strongly, but the mission's
  cost ceiling, not knowledge, currently bounds each run, so the curve
  shows in mapped ground rather than dollars.
- Moving decisions into deterministic machinery risks hiding failures
  instead of fixing them: confirmed the hard way. Aggregate numbers
  looked like progress while the transcripts showed a blind explorer
  driven by a broken instruction. Machinery without transcript-level
  verification, and without a success metric tied to the actual game
  goal, optimizes the wrong thing efficiently.
- Open: the knowledge contract needs a revision before more capability
  work: completeness (qualitative observations must become facts),
  access (the model must be able to read what it knows), and feedback
  (exploration must return experience, not geometry). The game strategy
  layer that week 0 held in prose has no carrier yet.

## Key Takeaway

Machinery made the agent cheap and safe before anyone checked whether it
understood the game; the transcripts showed it did not, and only reading
them revealed it.
