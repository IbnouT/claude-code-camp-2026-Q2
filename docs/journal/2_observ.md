# Week 2 Technical Documentation

## Technical Goal

- Make the agent observable end to end: capture what the game actually sent,
  what the agent believed, and what it cost, and be able to replay any run
  afterwards from that evidence.
- Build the foundation our web monitor (the Observatory) needs: every piece of
  evidence tied to exactly one player and one session.

## Technical Uncertainty

- I'm uncertain whether local instrumentation will actually explain the agent's
  behaviour, or just pile up logs nobody can read.
- I'm uncertain how much of the game's output can be understood with plain
  parsing, without paying a model to read it.
- I'm uncertain what really drives run cost. My assumption is bigger tool
  results mean bigger bills, but I haven't verified it.

## Technical Hypotheses

- A deterministic layer that sits on the telnet wire and types the game's
  output should remove repeated LLM work and make failures explainable.
- The hard part will be keeping the raw evidence for debugging without flooding
  the agent's context with it.

## Technical Observations

**The gateway**

This week is about observability, so we own the wire. Our gateway holds the
telnet session, records every byte in both directions, and types the output
into one per-session journal that both live view and replay read.
Detail: [gateway README](../../week2_capable/gateway/README.md).

- We tried shrinking the agent's tool surface by grouping related actions into
  fewer, bigger tools. It backfired: the tool count dropped but the schema grew
  to 7,494 bytes against 6,290 for the direct 25 tools, because the parameters
  and enums just move inside. We kept the direct surface.
- The colour of the game's ANSI text turned out to be a strong parsing signal.
  Room titles, combat, and prompts each have their own look, so colour-aware
  rules type about 86% of lines with no model call. The unmatched 14% keep their
  raw bytes, so the parser's blind spots are a list to fix, not silent loss.

**Benchmarks**

We benchmark short goal-driven journeys (find the bakery, read the menu),
judged from the recorded evidence, and reset the player to the same start
before every run. One early run silently started inside the bakery instead of
the Temple, and its results were worthless.
Detail: [benchmark plan](../plans/week2_observ/benchmark.md).

- We ran the same journey ten times per response style. Fully structured tool
  results are 59.8% larger than raw text, yet raw and full journey costs came
  out nearly equal, and the stripped-down "minimal" style was the most expensive
  of the three (28.6% over raw), because the agent needed 53.1% more calls to
  make up for the missing information. So we now judge a response style by the
  behaviour it produces over a whole journey, not by its size per message.
- We gave the agent a goal it couldn't easily reach: find the Massive Minotaur
  in the newbie zone. It gave up after 90 tool calls while reporting the journey
  as complete. That gap, believing it finished when it hadn't, is the central
  design idea of the Observatory's belief-versus-reality view.

**Multi-player foundation**

Two agents can play at once as different characters, and the Observatory
switches between them, so isolation had to be real rather than cosmetic.
Detail: [multiplayer plan](../plans/week2_observ/multiplayer.md).

- A per-character lock is held by the kernel, so two agents cannot drive the
  same character, and because the OS drops the lock when a process dies, a crash
  never leaves a character wedged. A hermetic two-agent test proves nothing
  leaks between players: files, costs, tokens, or knowledge.
- Reset restores a named baseline through a short-lived admin child, then
  reconnects and checks the result field by field before a run counts. When it
  fails halfway the session is quarantined and says so. We chose not to pretend
  a rollback happened, because the game itself cannot be rolled back.

**The Observatory**

The web monitor is being built against the mockups, starting from the shared
shell and design system.
Detail: [observatory README](../../week2_capable/observatory/README.md).

- Source health became useful when it moved beside the evidence it could
  weaken. Keeping it in the global header made instrumentation look like a
  destination instead of an explanation.
- Steering a live agent from the Observatory needed a labelling rule more than
  a transport: an operator message is recorded as operator guidance, so it can
  never masquerade as the agent's own reasoning, observed game state, or
  benchmark evidence when the session is replayed later.
- Live intervention became safe when it moved to the boundary between agent
  iterations. Guidance can enter as a labelled operator message, while an
  in-flight model request remains an honest non-interruptible fact.

## Technical Conclusions

- Filled at week's end.

## Key Takeaway

- Filled at week's end.
