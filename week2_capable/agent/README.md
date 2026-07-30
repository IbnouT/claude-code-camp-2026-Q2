# boukensha · the MUD journey agent

boukensha is a Python agent that plays a MUD game server under
natural-language instruction. This package is the week 1 baseline carried
forward: the complete agent loop with multi-provider model access, MCP-hosted
tools, context management, cost accounting and session logging.

```mermaid
flowchart LR
    User(["user"]) --> Iface["Interfaces<br/><small>REPL · TUI · CLI · run()</small>"]
    Iface --> Core["Agent core<br/><small>loop · context · logging</small>"]
    Cfg["Configuration<br/><small>settings · secrets · prompts</small>"] --> Core
    Core --> Model["Model access<br/><small>5 providers, REST</small>"]
    Core --> Tools["Tools<br/><small>MCP host</small>"]
    Tools --> GW["gateway<br/><small>MCP server</small>"] --> MUD(["MUD server"])
    Core -.session logs.-> Viewer["Log viewer"]
```

## Running

```bash
../bin/agent          # from anywhere: environment sync, then the REPL
uv run boukensha      # the same, from this folder
```

Arguments pass through to the app. The TUI, CLI and programmatic `run()`
entry points are described in the module docstrings under `boukensha/`.

## Configuration

Everything is in `.boukensha/settings.yaml` at the repository root, which is
self-documenting: active values are set, every optional key is shown commented
with its default. Secrets live in `.boukensha/.env`. `BOUKENSHA_DIR` points
the agent at a different configuration directory.

First run, in order:

1. Create `.boukensha/.env` next to `settings.yaml` with provider secrets and
   any shared player-profile secrets:

   | Variable | For |
   |---|---|
   | `ANTHROPIC_API_KEY` | the anthropic provider |
   | `GEMINI_API_KEY` | the gemini provider |
   | `OPENAI_API_KEY` | the openai provider |
   | `OLLAMA_API_KEY` | the ollama_cloud provider (local ollama needs none) |
   | `MUD_PASSWORD` | example player-profile password source |

   A player secret may instead live in
   `.boukensha/profiles/<profile>/.env`. The public character and its
   `password_env` name are configured under `gateway.players`.

2. Pick the model in `settings.yaml` under `tasks.player`: set `provider` and
   `model`. The alternatives are present as commented lines, switching is
   uncommenting one pair.

3. Install the gateway command from the repository root:

   ```bash
   uv tool install --editable ./week2_capable/gateway
   ```

   The isolated tool exposes `boukensha-gateway` on `PATH`. The default MCP
   entry starts it without repeated arguments. The `gateway:` block owns its
   connection, evidence, surface, API, and administrator settings.

4. Have the MUD server running.

5. Run `week2_capable/bin/agent`, then type a goal at the prompt.

The REPL and TUI use the same assembly path and therefore the same gateway
profile and tool set.

The gateway's typed result envelopes stay intact in model context and session
logs. The TUI unwraps their human text into rooms, messages and readable errors.

The full `tasks.<name>` reference (the agent plays the `player` task):

| Key | Default | Meaning |
|---|---|---|
| `provider` | (required) | `anthropic`, `gemini`, `openai`, `ollama`, or `ollama_cloud` |
| `model` | (required) | a model in the catalog (`boukensha/models.yaml` or a `.boukensha` override) |
| `prompt_override.system` | `false` | use `prompts/<task>/system.md` when present |
| `thinking` | unset | reasoning effort: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |
| `max_iterations` | `25` | tool-call rounds per turn (`0` disables) |
| `max_output_tokens` | `1024` | per-call output-token cap |
| `max_turn_tokens` | `60000` | per-turn work ceiling across every token class (`0` disables) |
| `max_turn_cost` | disabled | per-turn money ceiling in dollars |
| `compaction_threshold` | `0.85` | window fraction that triggers auto-compaction |

`agent:` holds agent-wide defaults for the five limits. Resolution is the
per-task value first, then `agent:`, then the code default.

The `mcp_servers.<name>` reference (every tool the agent has comes from an
entry here, so the game connection is configuration, not code):

| Key | Default | Meaning |
|---|---|---|
| `command` | (required) | an executable on PATH |
| `args` | `[]` | arguments passed to it |
| `env` | `{}` | exceptional per-process environment, secrets do not go here |
| `prefix` | none | agent-side tool-name prefix (`tbamud__look`) |
| `required` | `true` | `true` stops boot on a failed spawn, `false` warns and continues |
| `timeout` | `30` | per-call ceiling in seconds |
| `allow` / `deny` | none / `[]` | restrict or drop tool names |
| `result_mode` | `full` | model-facing results: `raw`, `minimal`, or `full` |

The context window is not a setting: it is a model fact read from the catalog.
The gateway configuration reference is in
`week2_capable/gateway/README.md`. The Observatory configuration reference is
in `week2_capable/observatory/README.md`.

## Tests

```bash
uv run pytest -q
```

pytest is a development-only dependency for Week 2 tests and collects the
carried unittest suite as well.

## Organization

```
agent/
├── boukensha/       the package: loop, context, backends, MCP host, logging
├── tests/           unit tests
├── pyproject.toml   project + pinned dependencies (uv.lock)
└── README.md        this file
```

Session logs land in `.boukensha/sessions/`, readable with the
[log viewer](../log_viewer/).
