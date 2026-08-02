---
name: journal-voice
description: Write or revise weekly technical journals under docs/journal. Use for every journal observation, conclusion, takeaway, journal quality review, or landing that must keep the current week's journal true.
---

# Journal voice

Write a navigable technical notebook of the challenge period. Help the
instructor understand why the repository took its current shape, follow the
evidence to the implementation, and determine the result.

## Read before writing

Read these sources completely:

1. `docs/journal/README.md`
2. The previous two weekly journals, when they exist
3. The current weekly journal
4. The plan, implementation, tests, report, and retained evidence relevant to
   the observation

Use `docs/journal/0_preweek.md` as the strongest narrative reference. Use
`docs/journal/1_baseline.md` for a longer step-oriented week.

Never write from a commit message or implementation summary alone.

## Build the weekly arc

Keep these sections connected:

- Technical Goal: state what the week is trying to achieve.
- Technical Uncertainty: name doubts that could produce failure or a dead end.
- Technical Hypotheses: make guesses that later evidence can support or reject.
- Technical Observations: record the challenge period, experiments, wrong
  turns, measurements, corrections, and consequences.
- Technical Conclusions: answer the original hypotheses and preserve remaining
  uncertainty.
- Key Takeaway: state the most important lesson in one sentence.

Do not let observations grow into an unrelated list. Extend the existing
challenge narrative when new evidence belongs to a problem already introduced.

## Qualify every observation

Include an observation only when it does at least one of these:

- exposes a central technical challenge
- records a failure, dead end, or surprising result
- reports a reproducible measurement that changed an assumption
- explains a course correction and the evidence that caused it
- establishes a consequential system boundary or limitation
- helps the instructor locate the implementation or proof behind a result

If a landing produces none of these, do not invent a lesson. Either connect its
real result to an existing observation or report that the landing does not yet
meet the journal requirement.

## Write observations as evidence

An important observation should make four things recoverable:

1. Challenge: what was uncertain, broken, or being tested
2. Evidence: what run, test, measurement, or retained record exposed it
3. Turning point: what assumption failed or what became clear
4. Result: what changed in the design, implementation, or remaining question

Link to the smallest useful repository artifact. Prefer a focused report,
README, plan section, test, screenshot, or benchmark over a directory link.
State caveats when the evidence does not support a general conclusion.

## Keep the register honest

- Use first person or first-person plural naturally.
- Be willing to record a wrong assumption.
- Prefer concrete numbers when they changed the decision.
- Distinguish implemented results from plans and open questions.
- Preserve ambiguity and missing evidence instead of resolving it rhetorically.
- Summarize large proof and link to it.

## Exclude material that belongs elsewhere

Do not add:

- changelog entries or commit summaries
- routine implementation details
- product requirements or acceptance criteria
- isolated UI rules and micro-interactions
- generic architecture maxims without the evidence that produced them
- coordination, approvals, reviews, branches, or work-management history
- unsupported measurements or reconstructed claims
- AI attribution or descriptions of who prompted a tool

Move product behavior to a plan or README. Move exhaustive measurements to a
report. Move verification mechanics to tests. The journal keeps only the
challenge, evidence, lesson, and result.

## Run the quality gate

Before finishing, verify:

- The instructor can navigate from each major challenge to its proof.
- The challenge period is visible, including wrong turns and corrections.
- The observations contain results, not only polished principles.
- Measurements have a method, source, or linked report.
- Implemented work and remaining plans are clearly separated.
- Conclusions answer the initial hypotheses.
- The takeaway follows from the week's strongest evidence.
- Removing any observation would not make the challenge harder to understand.

Read the complete journal once as one story. If it reads like a specification,
release log, or pile of unrelated lessons, revise it.
