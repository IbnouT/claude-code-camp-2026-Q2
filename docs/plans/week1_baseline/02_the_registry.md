# Step 02 · The registry — plan

## Goal

The tool registry: the component that holds the agent's tools and dispatches a
model's tool call to the right handler. It owns the tool table outright, so
tool lifecycle lives in one place. A shared `errors` module is introduced here
for the exception types more than one component raises.

## Deliverables

The step package carries step 01 forward and adds:

```
week1_baseline/agent/02_the_registry/
├── pyproject.toml
├── README.md                 # written from the built step
├── boukensha/
│   ├── __init__.py
│   ├── errors.py             # ConfigError, UnknownToolError, ToolArgumentError
│   ├── registry.py           # Registry
│   ├── config.py             # carried forward (imports ConfigError from errors)
│   ├── message.py            # carried forward
│   ├── tool.py               # carried forward
│   ├── context.py            # carried forward
│   └── tasks/                # carried forward
├── examples/
│   └── example.py            # runnable smoke test
```

The launcher: `week1_baseline/bin/02_the_registry`.

## Design

### Ownership: the registry holds the tools

The registry stores the tool table itself, in a `name → Tool` mapping. `Context`
does not hold tools, unchanged from step 01.

- One owner for the whole tool lifecycle: registration, lookup, dispatch.
- Nothing has to reach through `Context` to find a tool.

### Tool coherence

A tool's declared `parameters` are the schema the model is shown, so they must
match its handler. The check lives in `Tool` construction, not the registry,
because the data it needs is entirely the tool's own and the invariant holds
for every tool whether or not it is registered.

- Every required handler argument must be declared in `parameters`.
- Every declared parameter must be accepted by the handler, unless the handler
  takes `**kwargs`.
- A mismatch raises `ValueError` at construction, naming the tool and the
  offending arguments.

A schema that omits a required argument is the worst case: the model would be
handed a call it can never make valid, because it cannot supply an argument it
was never shown. Failing at construction keeps such a tool from existing.

### Registration

Two ways in, both landing in the same table:

- `register(tool)`: add an already-built `Tool`.
- `@registry.tool(name, description, parameters)`: a decorator that builds the
  `Tool` from the decorated function and registers it, returning the function
  unchanged. This is the ergonomic the standard tool library will lean on.

A duplicate name is rejected at registration, naming the tool. Two tools under
one name is never-valid data: dispatch could not choose between them.

### Dispatch

`dispatch(name, args)` resolves a call to a result:

- Unknown name raises `UnknownToolError`, naming the tool.
- Argument names are checked against the tool's declared `parameters`. An
  undeclared argument raises `ToolArgumentError`, naming the tool and the
  argument.
- The arguments are then bound to the handler's signature with
  `inspect.signature(...).bind(...)`. A binding failure, such as a missing
  required argument, raises `ToolArgumentError` naming the tool.
- Only after binding succeeds is the handler called, outside the check. A
  `TypeError` raised inside the handler's own body is a real bug and
  propagates honestly, never relabeled as an argument error.

Type and required-ness checks against the schema are not done here. The
parameter schema does not carry that information yet, so schema-based
validation waits until a later component enriches it. The name check and the
signature bind give a named, tool-specific error at the dispatch boundary,
which the agent loop can hand back to the model for self-correction.

### Errors module

`errors.py` holds the exception types shared across components: `ConfigError`
(moved from `config.py`), `UnknownToolError`, and `ToolArgumentError`.
`config.py` imports `ConfigError` from it, so the type is defined once and no
component reaches into another to raise a shared error.

## Verification

Launcher: `bin/02_the_registry` (wraps `uv run examples/example.py`).

| # | Assertion |
|---|---|
| 1 | a registered tool dispatches to its handler and returns its result |
| 2 | the `@tool` decorator registers the tool and returns the function callable |
| 3 | an unknown tool name raises `UnknownToolError` |
| 4 | registering a second tool under an existing name raises |
| 5 | dispatch with an undeclared argument raises `ToolArgumentError` |
| 6 | dispatch with a missing argument raises `ToolArgumentError` |
| 7 | `Context` still exposes no tool table (ownership stays in the registry) |
| 8 | a `TypeError` raised inside a handler's body propagates unrelabeled |
| 9 | a tool whose schema omits a required handler argument is rejected at construction |

## Done when

The launcher runs the example, all assertions pass, and the step README is
written from the built step.
