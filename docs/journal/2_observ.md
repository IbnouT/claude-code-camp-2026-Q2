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
- A cumulative cost curve can reconcile a run while the retained per-response
  fields remain materially lower. Keeping both values visible turns a silent
  mismatch into an instrumentation finding.
- Live intervention became safe when it moved to the boundary between agent
  iterations. Guidance can enter as a labelled operator message, while an
  in-flight model request remains an honest non-interruptible fact.
- Rendering the 1,878-room atlas was cheap, but it still could not locate the
  live agent without a retained stable room number. Scale and epistemic
  correlation are independent observability problems.
- A safe experiment runner needs two budget proofs: a preflight maximum
  derived from planned samples, and a runtime ledger that refuses the next
  sample unless its full ceiling still fits. One cumulative cap cannot prove
  both.
- Natural language is not the security boundary of an evidence copilot. The
  boundary is the typed query that carries its source and temporal scope
  through planning, optional translation, execution, and citation navigation.
  Validating only the first planner leaves a translated query able to cross
  the very boundary the interface promises.
- We ended up with two plausible sources of what a player knows, the cumulative
  per-player database and a projection recomputed from a single run, and they
  disagree by construction since a run only sees itself. The fix was rank, not
  merge: the database is the one authoritative source and the projection is
  demoted to a labelled per-session lens, so a reader cannot mistake one for
  the other.
- A stable live interface starts with a URL-backed identity and lifecycle
  boundary. Building that shell before its data regions prevents an empty map
  from looking authoritative and gives each later layer one explicit contract.
- Visual continuity depends on carrying the established component treatment,
  not merely its color tokens. Extra opacity or an eager responsive collapse
  can change the hierarchy even when every underlying color is identical.
- A session already owns its player, so presenting both as independent
  selectors creates impossible combinations. One context switcher makes the
  viewing identity atomic and gives each lifecycle state one valid action set.
- A growing map needs separate world and camera coordinates. Re-normalizing
  the whole drawing around new extrema moves every old room even when the
  layout itself is deterministic. Fixed world coordinates let the camera
  follow the agent without rewriting learned geography.
- Game sector flags describe engine terrain, not always the room a person sees.
  A reviewed observer-owned override lets the map call a sewer underground and
  a post office civic while preserving the original world files as evidence.
- Frontier marks become trustworthy when they are projected from retained
  exits after room identity is canonicalized. Drawing first and deduplicating
  later can make one learned doorway appear as several unknown paths.
- Map presentation and camera remain separate state, but their semantics are
  not always independent. Focus can permit bounded local inspection while
  Lantern cannot, because only Focus hides learned topology. Projecting that
  hidden topology from stable room positions against the live frame keeps its
  continuation cue truthful as the camera moves.
- A fixed inspector can preserve map context when its footprint becomes a
  camera inset rather than a layout mutation. The selected room stays visible,
  and the learned coordinates remain honest.
- Correct evidence can still look untrustworthy when observer facts and agent
  observations share one provenance list. A visible boundary in the interface
  should match the boundary in the data.
- A legend is evidence too. Deriving its rows from the active projection keeps
  hidden frontier and visit marks from being explained as if they were visible.
- Entering Manual is a behavior change, not a camera transform. Preserving the
  exact center and scale at the gesture boundary removes the jump that makes a
  map feel untrustworthy even when every coordinate is correct.
- A camera should measure the pane the investigator can actually see. Focus
  density belongs to room selection, not camera scale: complete shells can
  adapt around the actual overlay rectangles while the room size and Follow
  center remain stable. Treating a small dock as a full-width band discards
  useful map context without making any evidence safer. A room's title and
  badges belong to its fitted footprint because clipping them changes the
  evidence the room appears to carry. A geometrically valid fill can still
  lie about topology when it skips a bridge, so the projected set must also be
  the agent's connected component.
- Coordination needs one small authoritative turn record. Searching an
  append-only discussion log missed approvals and replies, while a four-line
  owner, ask, reference, and timestamp handoff made the next action explicit.
- A plausible measurement is not evidence when its capture is missing, its
  viewport differs from the product, or its replay exercises another client
  pipeline. Stating the gap is more useful than publishing a number that proves
  the wrong claim.
- An append-only log can retain every true event while a projection still
  invents a journey. Control receipts must be traversal boundaries, otherwise
  an administrator moving a player looks exactly like the player discovering
  a path.
- Live status is trustworthy only when each value keeps its own observation
  clock. Prompt vitals, score maxima, tool calls, and response economics can
  all be true at different moments.
- Continuous progress measurements make a threshold legible before it fires.
  Lifecycle and capture guards prevent those measurements from implying
  precision the retained prefix cannot support.
- Historical inspection needs two simultaneous truths: the selected prefix and
  the latest retained snapshot. Without the second, stepping backward erases
  the future landmarks needed to step forward or return to live.
- A compatibility field must preserve its original meaning across new control
  paths. Operator guidance is user-shaped prompt text, but treating it as the
  objective would make a Nudge silently rewrite the goal.
- A timestamped event belongs to the first replay prefix whose retained time
  includes it. Correlating operator control to the preceding gateway sequence
  draws a plausible marker that disappears when selected.

## Technical Conclusions

- Filled at week's end.

## Key Takeaway

- Filled at week's end.
