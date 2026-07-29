## Technical Goal

- Make the agent observable before making it more capable.
- Expose the bytes, commands, state, timing and cost of a run so a failure can
  be explained, not guessed.

## Technical Uncertainty

- Whether local instrumentation clarifies the agent's behaviour or just piles
  up logs.
- How much can be resolved without a model call.

## Technical Hypotheses

- A deterministic layer close to the game removes repeated LLM work.
- The hard part is keeping enough raw evidence to debug without flooding the
  agent with it.

## Technical Observations

- Replaced the mud_manager with our own gateway so we own the wire a run is
  observed and replayed from.
- Separating capabilities from advertised profiles made comparison cheap. The
  first fully validated grouped surface was larger than direct, 7,494 versus
  6,290 schema bytes, so tool count alone is not a cost result.
- Colour-aware rules typed 2,644 of 3,067 recorded lines without a model. The
  423 misses remain linked events, turning the 13.8% residual into a measured
  target instead of silent loss.
- Re-deriving the Week 1 baseline exposed 451 executed calls and 447 that
  reached later prompts, not the working figure of 448. A benchmark number
  without a traceable counting rule is another unobserved system state.
- The long probe crossed 17 rooms, then self-terminated after 90 calls without
  reaching its goal. The tracker kept the duplicate entrance ambiguous instead
  of inventing a location: a completed turn is not a completed journey.

## Technical Conclusions

- Filled at week's end.

## Key Takeaway

- Filled at week's end.
