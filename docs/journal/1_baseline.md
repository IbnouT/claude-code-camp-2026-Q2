# Week 1 Technical Documentation

## Technical Goal

Build the baseline agent in Python: the foundational components any agent needs, assembled one step at a time.

- Configuration, core data structures, and a tool registry
- Prompt building for multiple providers behind one interface, and the REST client
- The agent loop, JSONL session logging, a run() entry point, a REPL, and the installed command
- MCP-hosted tools connected to mud_manager, and context management

Detailed architecture: [architecture.md](../plans/week1_baseline/architecture.md)

## Technical Uncertainty

- I'm uncertain the MCP bridge between our Python agent and the Ruby mud_manager server will work cleanly, this combination is not validated anywhere.
- I'm uncertain multiple provider APIs can sit behind one normalized shape without their differences leaking, especially thinking modes and tool-call ids.
- I'm uncertain context compaction alone can keep long play sessions coherent with no memory layer underneath.

## Technical Hypotheses

- I think the agent loop and the normalized response contract will port cleanly.
- I think MCP interop will be the sticking point that costs the most debugging time.
- I think naive compaction would corrupt conversations by splitting a tool call from its result, so ours will have to drop messages pair-aware.

## Technical Observations

**General**

- Week tooling: Python, one self-contained uv project per step, a `bin/` launcher per step.
- One environment per step, by design: the steps are versions of the same `boukensha` package, and an environment can install only one version at a time. uv creates each venv lazily and hardlinks packages from its cache, so there is no real duplication on disk.

**Step 00 · Configuration**

- Built and verified: the example's assertions pass, an empty config directory runs on defaults, a malformed settings file fails naming the offending key.
- Credentials never sit in versioned files: the MUD password lives only in `.env`, and `.env.example` documents the required keys.
- Path ownership rule: `Config` owns every path under `.boukensha`, each package owns the paths of what it ships. The bundled default prompt moved inside the tasks package (via `importlib.resources`), where it also ships correctly in a built package, which it would not have from the step root.
- A task subclass that forgets its `task_name` now fails at class-definition time rather than resolving wrong paths silently.
- Config discovery now walks up from the current directory to the nearest `.boukensha`, like git finds its repo, so a project-local config needs no environment setup; the trade is that the found tree's `.env` gets loaded, so you trust where you run.
- Full detail in the step's [README](../../week1_baseline/agent/00_config/README.md).

**Step 01 · Struct skeleton**

- Built and verified: the example's nine assertions pass, covering normalization, every invariant rejection, immutability, and history order.
- Message content is one provider-neutral shape, a tuple of typed blocks (text, tool-use, tool-result), so downstream reads one dialect, each backend translates only at its own edge, and stored history stays portable across providers.
- Four invariants are enforced when a message is built, not at request time: a tool result must carry its `tool_use_id`, only a tool-result message may hold that content, a tool call may come only from the assistant, and content holds only typed blocks. Invalid conversation data cannot reach a provider as a 400.
- The call-to-result link lives only on the tool-result block, exposed as `tool_use_ids` (plural, for parallel calls), so there is no second copy to drift.
- Context stays conversation-only: the tool table, token counts, and turn counters each live with the component that owns them, so nothing is stored in two places.
- Full detail in the step's [README](../../week1_baseline/agent/01_struct_skeleton/README.md).

## Technical Conclusions

[todo]

## Key Takeaway

[todo]
