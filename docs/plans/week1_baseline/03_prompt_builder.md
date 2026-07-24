# Step 03 · Prompt builder plan

## Goal

Turn a `Context` into the request each provider expects, behind one interface.
Five providers (Anthropic, OpenAI, Gemini, Ollama, Ollama Cloud) differ in
where the system prompt goes, what the roles are called, how tools and tool
results are shaped, which key caps output tokens, and how they authenticate.
Each backend confines those differences to one place. Everything upstream
works in our own typed shapes.

## Scope

This step builds the request only. Response parsing is added with the
component that reads a response (the API client and agent loop).

## Deliverables

The step package carries step 02 forward and adds:

```
week1_baseline/agent/03_prompt_builder/
├── pyproject.toml
├── README.md
├── boukensha/
│   ├── backends/
│   │   ├── __init__.py        # backend_for(provider) factory
│   │   ├── base.py            # Backend interface, model metadata accessors
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   ├── gemini.py
│   │   ├── ollama.py
│   │   └── ollama_cloud.py
│   ├── models.py              # ModelCatalog
│   ├── models.yaml            # bundled model data: windows, costs
│   ├── prompt_builder.py      # PromptBuilder: binds context, backend, tools
│   ├── message.py             # carried forward, ToolResultBlock gains tool_name
│   ├── tool.py                # carried forward, gains required_parameters
│   └── ...                    # rest carried forward
├── examples/
│   └── example.py
```

The launcher: `week1_baseline/bin/03_prompt_builder`.

## Design

### One interface

`Backend` is an abstract base with one uniform surface, so no caller has to
know which provider it holds:

- `build_request(context, tools, max_output_tokens, thinking=None) -> dict`
- `headers() -> dict`
- `url() -> str`

The caller supplies the tools from the registry, so a request carries exactly
the toolset it was built with. The abstract methods raise
`NotImplementedError`, so a backend that misses one fails loudly rather than
diverging in signature. Each backend names the environment variable its key
comes from, and `backend_for` reads it: `Config` loads `.env` into the
environment, the backend knows which name is its own.

### Translation at the edge

Each backend maps our typed blocks to its wire format, the only place any
provider shape appears:

- `TextBlock` to the provider's text form.
- `ToolUseBlock` in an assistant turn to the provider's tool-call form.
- `ToolResultBlock` to the provider's tool-result form.

Because content is already typed blocks, an assistant turn that calls a tool
serializes correctly for every provider.

### Provider targets

- OpenAI is targeted through the Responses API. On current models, tool
  calling with reasoning available is only supported there.
- Gemini is targeted through `generateContent`, which remains fully supported.
  The backend boundary makes a future move to the Interactions API a one-file
  change. Revisit if a required model ships on Interactions only.

### Per-provider matrix

| Concern | Anthropic | OpenAI Responses | Gemini `generateContent` | Ollama / Cloud |
|---|---|---|---|---|
| endpoint | `/v1/messages` | `/v1/responses` | `models/{model}:generateContent` | `/api/chat` |
| system prompt | top-level `system` | top-level `instructions` | `systemInstruction` | `role: system` message |
| conversation | `messages` | `input` item array | `contents` | `messages` |
| assistant role | `assistant` | `assistant` | `model` | `assistant` |
| tool declaration | `input_schema` | **flattened** `function` item | `functionDeclarations` | nested `function` object |
| tool call carries | `input` object | `arguments` JSON **string**, `call_id` | `args` object, `id` | `arguments` object, **no id** |
| tool result | `tool_result` blocks in a user message, by `tool_use_id` | `function_call_output` item, by `call_id` | `functionResponse` part, name plus id echo | `role: tool` message, `tool_name` |
| several results in one message | one message, N blocks | **one item per result** | one message, N parts | **one message per result** |
| max output tokens | `max_tokens` | `max_output_tokens` | `generationConfig.maxOutputTokens` | `options.num_predict` |
| streaming default | off | off | off | **on**, so `stream: false` is always sent |
| auth | `x-api-key` + version header | `Bearer` | `x-goog-api-key` header | none / `Bearer` |

`OllamaCloud` subclasses `Ollama`, overriding only the URL and auth, since the
wire format is identical.

### Tool-result naming

A `ToolResultBlock` carries both halves of the link, set when the result is
created: the call id and the tool's name. `Message.tool_result(tool_use_id,
tool_name, content)` takes both.

- Gemini and Ollama key a result by the tool's name and read it directly from
  the block. Gemini gets the call id echoed as well, which current models
  require.
- A result missing either half is rejected when the message is built, so a
  request a provider would reject cryptically never gets assembled.

### Parallel results

One message may carry several `ToolResultBlock`s. Anthropic and Gemini take
them as blocks or parts of a single wire message. OpenAI requires one
`function_call_output` item per result and Ollama one `tool` message per
result, so those backends fan a single `Message` out. Our message count and
the wire item count are allowed to differ, and only the backend knows by how
much.

### Required parameters

The generated tool schema marks as required only the handler arguments that
have no default, read from the signature. A parameter with a default is
optional and is left out of `required`. `Tool` exposes `required_parameters`
for this, computed from the same signature its construction check already
inspects.

### Thinking

An optional per-task setting, `tasks.<task>.thinking`, with values `none`,
`minimal`, `low`, `medium`, `high`, `xhigh`, or `max`, one ordered dial. The
value is a ceiling on thinking depth, and each model delivers the most it
offers within it. `none` is the floor and turns thinking off where a model
supports that. `none` differs from leaving the setting unset: unset uses the
model's own default (for most models, to think), while `none` asks for no
thinking.

Unset is the default and means absence: requests carry no thinking and no
sampling fields, so each model's own default applies.

When set, the value flows as an optional `build_request` parameter. Each
model's thinking capability is catalog data, a `thinking` field on its entry,
and the backend maps its modes to the provider's documented form. A model
without the field gets nothing sent.

| Catalog mode | Models | Sent when set |
|---|---|---|
| `adaptive` | Claude Fable 5, Opus 4.6+, Sonnet 4.6+ | `thinking: {type: adaptive}` plus `output_config: {effort: <level>}`, and for `none`, `thinking: {type: disabled}` unless the model is always-on |
| `budget` | Claude Haiku 4.5, Opus 4.5 and earlier | `thinking: {type: enabled, budget_tokens}` with budgets 1024/4096/16384 for low/medium/high, and the field omitted for `none` |
| `effort` | OpenAI models | `reasoning: {effort: <level>}` |
| `level` | Gemini 3 and 2.5 families | `generationConfig.thinkingConfig.thinkingLevel: <level>` |
| `level_string` | `gpt-oss` | `think: "<level>"` |
| `flag` | qwen3, deepseek | `think: true`, or `think: false` for `none` |
| absent | gemma4, subscription models without documented support | nothing |

Each entry also lists `thinking_levels`, the level values the model's
documentation names (for example `none, low, medium, high, xhigh, max` on
current OpenAI models). The requested level is clamped onto that list:

- The model gets the highest supported level at or below the request, so a
  clamp never raises depth or spend above what was asked. `xhigh` on Haiku
  4.5 becomes `high`, and a gap is handled the same way, so `xhigh` on
  Sonnet 4.6 (which documents `max` but not `xhigh`) also becomes `high`.
- When every supported level sits above the request, the model's lowest
  supported level is used, since a set level always means some thinking.
- Entries without a list pass the request through unchanged.

`none` means no thinking, expressed as each provider and model allows:

- An off value where the provider has one: `reasoning: {effort: none}` on
  OpenAI, `think: false` on the Ollama flag models.
- An explicit disable where the model accepts it: `thinking: {type: disabled}`
  on the Anthropic adaptive models that can be disabled. This is required for
  the on-by-default model (Sonnet 5), where omitting would leave thinking on,
  and is used for the off-by-default models too so the request never depends
  on the default holding.
- An omitted field where omission is off: the Anthropic budget models, whose
  extended thinking is opt-in.
- The model's minimum where off is inexpressible: the always-on adaptive
  models (Fable 5) and the level models, which cannot be disabled.

Which case an Anthropic model falls into is read from its catalog
`thinking_default` (`off`, `on`, or `always_on`), the model's documented
default thinking state.

Per-model clamping is what lets the setting expose the full dial rather than
only the levels every provider shares: any value is safe on any model, so the
user picks a ceiling once and each model delivers the most it offers within
it, across model swaps.

Thinking capability lives in the catalog because it is per-model provider
data, the same kind as a context window: a new model with different thinking
behavior is a configuration edit. The Anthropic budget numbers are this
project's mapping, since the provider requires a number without prescribing
one.

The task layer gains a `thinking` accessor beside `provider` and `model`. It
returns `None` when the setting is absent, and rejects a value outside the
shared vocabulary with a `ConfigError` naming the task.

### Model catalog

Model metadata is configurable data, in a catalog with two layers:

- `boukensha/models.yaml`, bundled with the package: per provider and model,
  the context window, the USD cost per million input and output tokens, the
  usage unit (`tokens`, `local_compute`, or `subscription`, with an optional
  burn-rate `usage_level` on subscription models), the thinking form and
  levels, and, for Anthropic models, the `thinking_default` that governs
  disabling. Every value is taken from that model's own provider page, cited
  at the top of the file. Subscription models carry null costs, so an unknown
  price reports as no estimate rather than as free.
- `models.yaml` in the user's `.boukensha` directory, overriding or extending
  the bundled data per model. A new model is a configuration edit, never a
  code change. `Config.user_models_path` names the file, and the default
  catalog finds it through `Config.resolve_dir`, the one directory resolver
  every component shares, without loading anything else from the directory.

Backends expose the data as `context_window`, `usage_unit`, `usage_level`,
and `estimate_cost(input_tokens, output_tokens)`, which returns `None` for a
model without per-token pricing. A model missing from the catalog raises a
`ConfigError` at backend construction, naming the model and pointing at the
user catalog, so a misconfigured model fails before any request is attempted.

### Factory

`backend_for(provider, ...)` builds the right backend from a provider name, so
selection lives in the library rather than being repeated by every caller.

### PromptBuilder

`PromptBuilder(context, backend, tools)` binds the three things a request
needs, the conversation, the backend, and the toolset, so a caller asks one
object for a ready request instead of assembling the trio itself.
`build_request(max_output_tokens, thinking=None)` forwards to the backend with
the bound context and tools, and `headers` and `url` expose the transport
surface.

## Verification

Launcher: `bin/03_prompt_builder`.

| # | Assertion |
|---|---|
| 1 | Anthropic request puts the system prompt in top-level `system` and a tool result in a `user` message keyed by `tool_use_id` |
| 2 | OpenAI request puts the system prompt in top-level `instructions`, the conversation in `input` items, the cap in `max_output_tokens`, and a tool result as a `function_call_output` item keyed by `call_id` |
| 3 | Gemini request uses `systemInstruction`, the `model` role, and a `functionResponse` carrying the tool's name with the call id echoed |
| 4 | Ollama and Ollama Cloud send `stream: false`, key a tool result by `tool_name`, and differ only in URL and auth |
| 5 | an assistant `ToolUseBlock` serializes to each provider's tool-call form, with OpenAI's flattened declaration and `arguments` as a JSON string |
| 6 | a tool with an optional parameter (handler default) omits it from the schema's `required` |
| 7 | `backend_for` returns the matching backend and raises on an unknown provider |
| 8 | every backend exposes `build_request`, `headers`, `url` with the same signature |
| 9 | auth matches the provider: `x-api-key` header, `Bearer` header, `x-goog-api-key` header, or none |
| 10 | a message with two tool results stays one wire message on Anthropic and Gemini and fans out to two items or messages on OpenAI and Ollama |
| 11 | a tool result without a tool name is rejected at construction |
| 12 | with thinking unset, no request from any backend carries a thinking or sampling field |
| 13 | with thinking set, each catalog mode maps to its documented form, including adaptive plus `output_config.effort` on Fable 5 and `enabled` with budget on Haiku 4.5 |
| 14 | with thinking set on a model without the capability (gemma4), the request carries no thinking field |
| 15 | a known model resolves its context window, cost, and usage unit, and a subscription model reports no per-token estimate |
| 16 | an unknown model raises `ConfigError` naming it |
| 17 | the user catalog overrides and extends the bundled one |
| 18 | a level above the model's ceiling clamps to its highest at or below the request, never up |
| 19 | a level below the model's minimum uses its lowest supported level |
| 20 | `none` disables thinking: OpenAI `effort: none`, flag `think: false`, budget models omit the field |
| 21 | `none` on an always-on model (Fable 5) falls to its minimum level, not off |
| 22 | `none` on a disable-capable adaptive model (off-default Opus 4.8 and on-default Sonnet 5) sends `thinking: {type: disabled}` |
| 23 | a level outside the dial vocabulary is rejected, naming the valid values |

## Done when

The launcher runs the example, all assertions pass, prior steps still pass, and
the step README is written from the built step.
