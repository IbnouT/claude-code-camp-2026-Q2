# Week 3 · Knowledge rework

This plan corrects the knowledge design against the audited failures in
[the capability audit](../../reports/week3_capability_audit.md). It
states, in full detail, what each part must become. The parent
[knowledge plan](knowledge.md) still governs the architecture (five
capabilities, four seams, no prose pattern-matching in agent behavior);
this plan revises the knowledge contract, the exploration contract, the
strategy carrier, and the knowledge surface.

## 1. The knowledge contract: the store is the agent's memory

Principle: anything the game shows that a playing human would remember
must become a typed fact. The session log is evidence for auditing; it
is never the agent's memory. A fact that exists only in the log does not
exist for the agent.

What the store holds today: room titles, descriptions, exit lists, exit
links, sighted creature and object names, own vitals and score numbers.

What it must additionally hold, each with its source:

| Fact | Subject and predicate shape | Source |
| --- | --- | --- |
| Room is dark or perception failed there | place · quality.dark | structural signal only: movement points were spent and no room parsed, which also separates dark from a refused move (a refusal costs nothing); corroborated by the model's perception note and the carried-light correlation. The week 2 pitch-black phrase rule stays journal-only: no behavior and no fact may depend on it, and the position tracker's current use of it moves to the movement-cost signal |
| Sign and board text | place · sign.text | the model reads the prose and records it through its note tool |
| Shop stock and prices | place · stock.[item, price] rows | the shop list command's output when visited |
| Monster appraisal | entity · consider_at_level_N · verdict tier | the consider command, read by the model, recorded as a typed tier |
| Door state per exit | place · door.[direction] · open, closed, locked | movement refusals and open and unlock attempts |
| Item taken or seen in detail | entity facts from examine and inventory | the examine and inventory commands when used |
| Area membership hints | place · area · free text | the model's note when it recognizes a district (a sewer, a shop street, a temple quarter) |
| Aggression | entity · attacks_on_sight · true | an unprovoked combat start in that entity's presence |

Provenance rules stay as built: parser-derived facts are learned or
parsed; model-derived facts are beliefs with low confidence; every fact
carries its session evidence.

## 2. Model access: the agent can read what it knows

The model needs a query tool, not a bigger summary. One tool, `recall`,
with a small closed set of typed queries:

| Query | Returns |
| --- | --- |
| room, by title or here | everything known about one room: exits and where they lead, creatures and objects seen there with last-seen time, qualities, signs, notes |
| creatures | every sighted creature, its rooms, any appraisal tiers |
| services | recorded shops, banks, guilds, fountains, healers, grinding spots, each with its room |
| target, by name | sightings of the named target with rooms and times |
| unexplored | the nearest rooms that still have unexplored exits, with distance |
| self | the character sheet: level, vitals against maxima, gold, known skills, equipment |

Results are compact prose lines (readable, not JSON), each derived from
facts, capped in length, ordered by relevance. The week 0 rule carries
over as behavior: the standing instruction tells the model to recall
before deciding, and the state block's last line names the tool.

## 3. The exploration contract: sweeps return experience, not geometry

The sweep report must let the model steer and notice. Its report gains:

- rooms visited, by title, in walk order, with area transitions marked
- creatures seen during the walk, each with the room it stood in
- objects seen, each with its room
- anything that interrupted or refused movement, in typed form
- the current standing summary it already has: steps, new rooms,
  frontier remaining, stop reason

Sweep behavior changes:

- an optional target argument: when a sighting matching the target name
  is recorded during the sweep, the sweep stops immediately with the
  typed stop `target_sighted` and the room named
- an optional direction or area preference, so the model can steer
  ("sweep toward the exits leading out of the city", "prefer down")
  expressed as a starting frontier choice, never prose parsing
- posture is checked before every step; a resting or sitting character
  stands first
- a refused step records the refusing direction as untraversable for
  this sweep, so the same closed door is never retried within one run

## 4. The strategy carrier: the week 0 rules get a home

The authored rules layer from the parent plan is built, with the week 0
play skill as its source text, generalized to genre common sense:

- consider before every deliberate fight; the appraisal tiers gate
  engagement, and the worst acceptable tier is a setting
- an unbeatable target means leveling or better equipment first, never
  a retry
- carried gold is lost on death: bank surplus above the ceiling
- rest before exploring when movement is low; eat and drink when hungry
- collect obvious free equipment before hunting (a donation room is the
  canonical example)
- loot after kills: corpses carry gold, keys, and gear
- experience per kill falling means the targets are outleveled: move up

Delivery: the rules ride the state block as one standing compact section
(they are short); each rule has an id, and reflex or gate decisions cite
the rule id in their journal events.

The readiness gate becomes real: the campaign phase function orders
prepare before locate for an unready character, where unready is typed:
no weapon or armor equipped, level below the target floor setting, gold
below a basics floor, or a target appraisal at the forbidden tier. Each
gate reads facts (equipment from the equipment check, level and gold
from score, appraisals from recorded considers). The engage phase
requires a fresh appraisal at an acceptable tier before attack.

## 5. The knowledge surface: a knowledge base, not a table

The page scrolls like any document page. The route restores normal page
scrolling exactly as Sessions does.

The space is organized by meaning, with lenses:

- World: one card per known room, titled by room name, showing its exits
  and where each leads (or that it is unexplored), the creatures and
  objects seen there with last-seen times, its qualities (dark, area),
  signs, and any notes or beliefs attached, each with its evidence link.
  Cards group by area when area facts exist, and a search filters by any
  of it. Room identity strings never appear as primary labels; titles
  do, with the identity available in a detail view.
- Character: one sheet assembled from facts: level, vitals against
  maxima, gold, skills, equipment, with the session evidence for each
  value and its history where retained.
- Beliefs: the agent's own assertions and appraisals as readable
  statements ("the sewer entrance is dark", "the cityguard at the gate
  is deadly at level 3"), each with confidence, age, evidence, and any
  conflicting observation shown beside it.
- Services: the recorded map of where to buy, bank, train, drink, and
  grind, each entry naming its room and the evidence.

Every value on every lens links to the session evidence that produced
it, reusing the existing evidence-link pattern from Sessions.

## 6. Wiring corrections

- The agent-side fetchers unwrap the gateway result envelope and consume
  the inner text for both the state block and the readiness report.
- The per-response STATE line is withdrawn. Its three fields move into
  the existing note tool as arguments the model supplies when something
  changed, and the state block reminds the model of the duty. A required
  text line on tool-calling responses conflicts with tool use and does
  not return.
- Routines check posture before stepping.
- The knowledge page scroll defect is fixed with the surface rework.

## 7. Verification standard for this rework

- Every landed step is verified against at least one full session
  transcript, read message by message, not from ledger aggregates.
- The mission metrics that matter are game progress: levels gained,
  gold held and banked, kills, equipment worn, target sighted, target
  killed. Call counts and cost remain reported but never stand alone.
- The knowledge surface is verified by using it as a person: scrolled,
  searched, read, in both themes, against the real store.
