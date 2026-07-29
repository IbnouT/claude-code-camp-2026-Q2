# Gateway journey benchmark

The benchmark measures correct game journeys and total model cost through the
same installed gateway used by the agent REPL and TUI.

```mermaid
flowchart LR
    B["E1 harness"] -->|"private reset"| A["gateway admin"]
    B -->|"one agent turn"| P["Boukensha"]
    P -->|"MCP direct-full"| G["gateway"]
    A --> M["MUD"]
    G --> M
    P --> L["agent JSONL"]
    G --> J["gateway SQLite"]
    B --> L
    B --> J
```

## Setup

Install the gateway and benchmark as isolated user tools from the repository
root:

```console
uv tool install --editable ./week2_capable/gateway --force
uv tool install --editable ./week2_capable/benchmark --force
```

The repository `.boukensha/.env` supplies provider and MUD credentials to a
live run. The benchmark overlay copies public settings only.

## Run

The default command is free. It proves the installed 25-tool `direct-full`
surface and audits the tracked Week 1 corpus:

```console
boukensha-e1
```

A live attempt requires both an explicit spend flag and a cumulative cap:

```console
uv run --no-project --env-file .boukensha/.env boukensha-e1 --spend --cap 10
```

`--result-mode raw|minimal|full` selects the model-facing result shape for an
isolated run. The gateway journal always retains the complete typed envelope.
Use a fresh `--output-dir` for every measured mode.

`--runs N` sets the target priced journey sample count for that output ledger.
A partial ledger can resume toward the same target:

```console
uv run --no-project --env-file .boukensha/.env boukensha-e1 \
  --spend --cap 3 --result-mode raw --runs 10 \
  --output-dir .boukensha/benchmarks/e1-render-raw-n10
```

Runtime artifacts go under `.boukensha/benchmarks/e1/`. A reset failure blocks
the agent process, is counted separately from journey outcomes, and stops the
batch for correction. It does not consume the requested sample count. An
unpriced model attempt is recorded for diagnosis but stops the paid sequence
and never enters aggregates.

Schema bytes are measured from the generated MCP JSON. The token field is an
explicit four-bytes-per-token estimate, so it is useful for comparing stable
profiles without pretending to be a provider tokenizer bill.

Multi-run reports include success rate and the mean, median and sample standard
deviation for cost, calls, correction counts and token classes.
