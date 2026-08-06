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

## Technical Conclusions

Open. The week is in flight, and the conclusions must answer the
hypotheses from the measured before and after of each landed capability.

## Key Takeaway

Open until the week closes.
