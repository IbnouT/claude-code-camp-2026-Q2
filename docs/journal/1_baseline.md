# Week 1 Technical Documentation

## Technical Goal

Build the baseline agent in Python: the foundational components any agent needs, assembled one step at a time. The build ports the bootcamp's Ruby baseline component by component, applying Python best practices and our design decisions where they improve the result.

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

- Python, one self-contained uv project per step, a `bin/` launcher per step.
- One environment per step: the steps are versions of the same package, and one environment cannot hold two versions. uv's cache makes the duplication near free.

**Step 00 · Configuration**

- Credentials live only in `.env`, never in versioned files. `.env.example` lists the required keys.
- Config discovery walks up from the current directory, like git. A project-local config needs no setup, and the found tree's `.env` is loaded, so you trust where you run.
- Path ownership: `Config` owns every path under `.boukensha`, each package ships and owns its own assets.
- Detail: [step README](../../week1_baseline/agent/00_config/README.md).

**Step 01 · Struct skeleton**

- Message content is a tuple of typed blocks, one shape for every reader, history portable across providers.
- Invalid messages cannot be built: role rules, tool linkage, and element types are all checked at construction.
- The call-to-result link is stored once, on the result block, read back as `tool_use_ids`.
- Context holds conversation state only, everything else lives with its owning component.
- Detail: [step README](../../week1_baseline/agent/01_struct_skeleton/README.md).

**Step 02 · The registry**

- The registry owns the tool table: registration, lookup, and dispatch in one place.
- One guard per failure class: schema-handler coherence at Tool construction, contract check and signature bind at dispatch, handler bugs propagate unrelabeled so the model's recovery is not misdirected.
- A schema that disagrees with its handler gives the model a call it can never make valid. Caught when the Tool is built, so it cannot exist at run time.
- Detail: [step README](../../week1_baseline/agent/02_the_registry/README.md).

## Technical Conclusions

[todo]

## Key Takeaway

[todo]
