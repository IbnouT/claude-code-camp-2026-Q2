# Week 1 Technical Documentation

## Technical Goal

Build the baseline agent in Python: every foundational piece an agent needs, added one step at a time as a working version we can run and test. By the end of the week the agent plays the MUD through its own loop, keeps a long session inside the context window, tracks what it costs, and can be watched live and read back afterwards.

- The core: typed messages, a tool registry, a prompt builder and REST client reaching all five providers through one interface, and the agent loop that ties them together.
- Running it for real: JSONL session logging, a run() entry point, an interactive REPL, a global command, and MCP-hosted tools to drive the MUD.
- Playing long: context management to hold a session as the window fills, cost accounting to see what it spends, a live terminal view of the journey, and a standalone log viewer to read a finished run.

Detailed architecture: [architecture.md](../plans/week1_baseline/architecture.md)

## Technical Uncertainty

- With this many moving parts (five backends, an MCP server in another language, the loop, compaction, cost accounting, the live views), how hard will it be to debug a failure end to end and tell which part caused it.
- Whether an architecture generic enough to run any provider can still drive the agent efficiently, or whether the generality gets in the way.
- How to build cost control that does more than report spend, that keeps the agent inside its limits and behaves sensibly when it hits them.
- I'm uncertain five provider APIs can stay hidden behind one message shape, thinking modes and tool-call ids are the likeliest to leak.
- I'm uncertain compaction alone can hold a long session, since dropping old turns to free space also drops what the agent learned, and there is no memory store underneath.

## Technical Hypotheses

- The live views and the logs, not any one component being right first time, will be what makes end-to-end debugging workable.
- The generic multi-provider shape will hold only if each provider's oddities (thinking, tool-call ids) stay inside its backend instead of leaking into shared code.
- Reporting spend will be the easy half. The ceilings that actually stop the agent will be the work, and one token count will mislead once caching is on.
- Dropping the oldest turns by age will corrupt a session, so compaction will have to cut on turn boundaries and leave a note for what it drops.

## Technical Observations

**General**

- Each step is a self-contained uv project with its own `bin/` launcher and its own environment, since the steps are successive versions of one package. uv's cache makes the duplication cheap.

**Step 00 · Configuration**

- Credentials live only in `.env`, never versioned, with `.env.example` listing the keys.
- Config is found by walking up from the current directory like git, so running inside a project uses its config with no setup.
- `Config` owns every path under `.boukensha`, and each package ships its own assets, so paths are never guessed at the call site.
- Detail: [step README](../../week1_baseline/agent/00_config/README.md).

**Step 01 · Struct skeleton**

- Message content is a list of typed blocks (text, tool call, tool result), read the same way everywhere and portable across providers.
- Messages are validated as they are built (role rules, the link from a tool call to its result, and block types), so a malformed message cannot exist.
- The call-to-result link is stored once, on the result, so the two never drift apart.
- Detail: [step README](../../week1_baseline/agent/01_struct_skeleton/README.md).

**Step 02 · The registry**

- One registry registers, looks up, and dispatches every tool in one place.
- A tool whose schema does not match its handler fails when built, not at run time, so the model is never offered a call it cannot make correctly.
- A bug inside a handler surfaces as the real error rather than being relabeled as a tool failure, so the model's recovery is not sent in the wrong direction.
- Detail: [step README](../../week1_baseline/agent/02_the_registry/README.md).

**Step 03 · Prompt builder**

- Each provider's wire format lives in one backend file, so switching provider or absorbing an API change touches one file.
- One typed message serializes to every provider's JSON, including an assistant turn with several parallel tool calls.
- Model settings are data (`models.yaml` plus a `.boukensha` override), so adding a model is an edit and an unknown one fails at startup naming the fix.
- Thinking has three states: unset uses the model default, none turns it off, and a requested level is capped to what the model supports.
- Detail: [step README](../../week1_baseline/agent/03_prompt_builder/README.md).

**Step 04 · API client**

- The client is provider-blind: URL, headers, and body come from the prompt builder, so one client serves all five backends.
- Transport and sleep are injected, so the full retry schedule is tested offline with no keys, sockets, or waiting.
- A connection cut mid-response can surface as more than a plain socket error (an HTTP exception, or an unexpected end of data), so the retry logic treats those as transient too instead of crashing.
- Detail: [step README](../../week1_baseline/agent/04_api_client/README.md).

**Step 05 · Agent loop**

- The loop parses each response into typed blocks, so the whole turn stays in the typed model, not raw dicts.
- The turn limit is a trigger, not a hard stop: at the limit the agent makes one final tools-off call to wind down instead of erroring mid-conversation.
- That wind-down call uses a toolless prompt builder, so the model cannot call a tool on the way out.
- Models that think within a token budget need the output cap raised, since providers count thinking tokens against the output limit and would otherwise leave no room for the reply.
- Detail: [step README](../../week1_baseline/agent/05_agent_loop/README.md).

**Step 06 · The Logger**

- One JSONL file per session, one flushed line per event, so a crash leaves a readable prefix and a session reads with `tail` or `grep`.
- The logger is also an event stream: each written event is handed to subscribers, guarded individually. Every later live surface builds on this hook.
- A logging failure records a `log_error` line instead of taking down the turn.
- Event types are defined once here, so the logger is one shared file across steps instead of copies that drift.
- Detail: [step README](../../week1_baseline/agent/06_the_logger/README.md).

**Step 07 · The Run DSL**

- `run(task=..., setup=...)` collapses the whole setup into one call, exposing a single method to register inline tools without touching the registry.
- The ollama host setting goes through one hook every backend implements, which removed an if-the-provider-is-ollama special case from the shared code.
- Config is read fresh per call, so a stale `.env` cannot leak across calls that change the config directory.
- Detail: [step README](../../week1_baseline/agent/07_the_run_dsl/README.md).

**Step 08 · The REPL Loop**

- Saving the final reply into context on every exit path is what makes multi-turn memory real.
- Slash commands live in a table, so `/help` never drifts, and `//` escapes one slash so an in-character line still reaches the agent.
- The activity feed is the first consumer of the event stream, and `/quiet` hides only the display while accounting keeps running.
- Ctrl-C cancels one turn back to the prompt, and `/undo` and `/retry` step a turn back through one context operation.
- Detail: [step README](../../week1_baseline/agent/08_the_repl_loop/README.md).

**Step 09 · The Global Executable**

- One `project.scripts` entry makes `boukensha` global, and Python's import order lets the step folder on the path take precedence over the installed package.
- Startup is tested offline by booting this step's own package through the real command against a stub transport.
- `python -m boukensha` uses the same entry point as the command, so the two cannot diverge.
- Detail: [step README](../../week1_baseline/agent/09_global_executable/README.md).

**Step 10 · The Standard Tool Library**

- The agent ships no tools of its own. Every capability is an MCP server named in config, so adding one is a config edit.
- The server is read on its own thread under a small client, giving per-call timeouts and crash detection a blocking loop cannot. A timeout, crash, or protocol error comes back as an ordinary `ERROR` result, so normal recovery continues.
- A duplicate tool name is fatal even for an optional server, since silently dropping one is expensive to debug later.
- The example is real cross-language interop: the Python host starts the Ruby mud-manager, handshakes, and calls a tool with no model in the loop.
- Detail: [step README](../../week1_baseline/agent/10_standard_tool_library/README.md).

**Step 11 · The Journey (TUI)**

- The TUI is a readable live view, not a debug console: two tabs (Dashboard, Feed) show the current room, the humanized action, thinking, vitals, status, goal, and a fight box, while the full trace stays in the logs.
- One presenter turns events into room, action, thinking, and combat cards, and token or iteration events produce none, so noise never reaches the screen.
- The thinking panel follows the agent's latest text each response. Getting there meant silencing the REPL feed inside the TUI, which had been overwriting it.
- Combat is detected by matching combat verbs in a recent window, so the fight box turns off when fighting stops and a reconnect menu never lands in it.
- Detail: [step README](../../week1_baseline/agent/11_tui/README.md).

**Step 12 · Context Management**

- Compaction is by meaning, not age: shorten the oldest tool-result bodies first, drop whole turns only if still over budget, and leave a note for anything dropped, so the agent does not re-search a room it already searched.
- The parser that draws the live view is also the memory, so the note is built from state we parse anyway, with no extra model call.
- A cut must land on a user turn. Cutting anywhere else separates a tool result from its call, which providers reject, so this is correctness, not tidiness.
- Every turn records why it ended, since a turn stopped by a limit otherwise looks like the agent deciding it was done.
- Detail: [step README](../../week1_baseline/agent/12_context/README.md).

**Step 13 · Context economics**

- A chat API re-sends the whole conversation every call, so a long turn pays for its history many times. Caching does not cut the tokens sent, it cuts their price, so cost and work are measured separately.
- Tokens split into four priced kinds: fresh input, cache read, cache write, and output. Providers name and total these differently, so we normalize once.
- Four numbers, none derived from another: work done (all tokens), window fill (the whole prompt), cost (each kind at its rate), and how much was new. Counting only fresh input would understate the same work once cached.
- New work against total work explains a surprising bill: one turn processed 2.15 million tokens for under five cents, 97 percent of them served from cache.
- Detail: [step README](../../week1_baseline/agent/13_context_economics/README.md).

**Log viewer**

- A separate program that reads a finished run's JSONL log and serves it in the browser, leading with what failed, what limited the run, and what was slow or expensive.
- It imports nothing from the agent. Its only tie is the log format, and it finds the sessions directory by the same rules, reimplemented.
- A session opens on a turn-by-turn narrative, with nine further lenses over the same record: the route on a map, the player's experience, prompt growth against the window, wall-clock time per call, what each prompt added, one tool's use, every movement and what the world said back, errors and tripped limits, and the raw events.
- The map does not trust room titles, since many rooms share one. It identifies a room by number and exits from the MUD's world files, and says so where those files are missing rather than drawing a false path.
- The player view computes six findings and prints the rule beside each: confused (a room entered three or more times), blocked (the same action refused twice or more), bored (four identical actions in a row), stuck (eight or more actions in a turn reaching at most one new room), overpowered (a zone named above the agent's level), and drained (the game reporting exhaustion).
- Slow or expensive turns are flagged against the session's own median, so a costly run does not flag every turn and a cheap one still flags its worst.
- Detail: [log viewer README](../../week1_baseline/log_viewer/README.md).

## Technical Conclusions

- Watching runs through the live view and the log viewer surfaced problems the tests had not, and several fixes came from watching.
- Cost control went as guessed: reporting spend was the easy half, and the work was counting tokens in classes so caching does not fool the measure and setting ceilings that actually bind.
- Compaction also went as guessed: dropping by age corrupts a session, and keeping tool-call pairs together was necessary but not enough, the cut has to reach a user turn. The note distilled from the parser we already run held sessions coherent with no separate memory store.
- Set aside for later: whether the player findings thresholds hold outside Midgaard's starting zone, and whether streaming would improve the TUI enough to justify a streaming path in all five backends.

## Key Takeaway

The baseline runs and can measure what it spends, but it holds its whole world in the passing conversation and calls the model for every step, so a longer goal will need what it still lacks: a lasting memory of the world it has seen, and a cheaper way to read a room than asking the model each time.
