# 02 · The registry

The registry holds the agent's tools and dispatches a model's tool call to the
right handler. The agent never calls a tool directly: it emits a name and a set
of arguments, and the registry looks the tool up, checks the call, runs it, and
returns the result. This step also introduces a shared `errors` module for the
exception types more than one component raises.

## New files

| File | What it adds |
|---|---|
| `boukensha/registry.py` | `Registry`, the `name -> Tool` table with registration, lookup, and dispatch |
| `boukensha/errors.py` | `ConfigError`, `UnknownToolError`, `ToolArgumentError`, each defined once |

## Updated files

| File | Change vs step 01 |
|---|---|
| `boukensha/tool.py` | `Tool` now validates at construction that its schema matches its handler |
| `boukensha/config.py` | imports `ConfigError` from `errors.py` instead of defining it |
| `boukensha/tasks/base.py` | imports `ConfigError` from `errors.py` |
| `boukensha/__init__.py` | exports `Registry` and the three error types |
| `examples/example.py` | registers tools two ways, dispatches them, walks the dispatch boundary |

`message.py`, `context.py`, `tasks/player.py`, `tasks/prompts/system.md`,
`pyproject.toml`, and `uv.lock` are carried forward from step 01 unchanged.

## How it works

The table sits at the center: registration writes into it, dispatch reads from
it, and each guard on the path fails with a named error.

```mermaid
flowchart TB
    dec["@registry.tool(name, ...)"] -->|builds Tool| regf["register(tool)"]
    obj["register(existing Tool)"] --> regf
    regf --> dup{"name already<br/>in table?"}
    dup -->|yes| rerr["ValueError, duplicate"]
    dup -->|no| TABLE[("tool table<br/>name → Tool")]

    call["dispatch(name, args)"] --> known{"name in table?"}
    TABLE -.lookup.-> known
    known -->|no| e1["UnknownToolError"]
    known -->|yes| declared{"args all declared?"}
    declared -->|no| e2["ToolArgumentError"]
    declared -->|yes| binds{"args bind to signature?"}
    binds -->|no| e3["ToolArgumentError"]
    binds -->|yes| run["handler(**args)"]
    run -->|handler raises| passthru["error propagates unchanged"]
    run -->|returns| result(["result"])

    ctor["Tool(...): schema matches<br/>handler, else ValueError"] -.-> obj
    ctor -.guarantees the schema<br/>a call is checked against.-> declared
```

Construction validates that a tool's schema matches its handler, so every tool
in the table can be called correctly, and the "args all declared?" guard checks
a call against a schema the model can actually satisfy.

## Ownership

The registry owns the tool table outright. `Context` holds no tools.

- One owner for the whole tool lifecycle: registration, lookup, dispatch.
- Nothing reaches through `Context` to find a tool.

## Registration

Two ways in, both landing in the same table:

| Entry | Use |
|---|---|
| `register(tool)` | add an already-built `Tool` |
| `@registry.tool(name, description, parameters)` | build the `Tool` from the decorated function and register it, returning the function unchanged |

A duplicate name is rejected at registration. Two tools under one name is
never-valid data, because dispatch could not choose between them.

## Tool coherence

A tool's declared `parameters` are the schema the model sees, so they must match
its handler. `Tool` checks this at construction, since the data is the tool's
own and the invariant holds whether or not the tool is registered.

- Every required handler argument must be declared in `parameters`.
- Every declared parameter must be accepted by the handler, unless it takes
  `**kwargs`.
- A mismatch raises `ValueError`, naming the tool and the arguments.

A schema that omits a required argument would hand the model a call it can never
make valid, so such a tool is rejected before it exists.

## Dispatch

`dispatch(name, args)` resolves a call to a result, with a named error at each
failure the model can cause:

| Situation | Result |
|---|---|
| known tool, valid arguments | the handler runs, its return value is the result |
| unknown name | `UnknownToolError`, naming the tool |
| an undeclared argument | `ToolArgumentError`, naming the tool and the argument |
| a missing required argument | `ToolArgumentError`, naming the tool |
| a bug inside the handler's body | the handler's own error propagates unchanged |

Arguments are checked by name, then bound to the handler's signature with
`inspect.signature`. The handler runs only after binding succeeds, so a
`TypeError` from a real bug in its body is never relabeled as an argument error.
The name check and the bind give a tool-specific error at the dispatch boundary,
which the agent loop can hand back to the model for self-correction.

Schema-based type and required-ness checks are deliberately not here. The
parameter schema does not carry that information yet, so those wait for the
component that enriches it.

## Errors

`errors.py` holds the exception types more than one component raises:

| Error | Raised when |
|---|---|
| `ConfigError` | a configuration file is malformed |
| `UnknownToolError` | dispatch is asked for an unregistered tool |
| `ToolArgumentError` | a tool is called with arguments that do not match |

Each type is defined once, so no component reaches into another to raise a
shared error. `config.py` and `tasks/base.py` now import `ConfigError` from
here.

## Sample output

The example registers `move` and `shout`, dispatches them, then walks the
dispatch boundary so each failure prints as a named error:

```
=== boukensha · step 02: the registry ===

Config:   <boukensha.Config dir=/path/to/repo/.boukensha tasks=player>

-- registered tools --
Registry: <Registry tools=['move', 'shout']>
  <Tool name=move description='Move the player in a direction.' params=['direction']>
  <Tool name=shout description='Shout a message to the zone.' params=['message']>

-- dispatch --
move   direction='north'         -> You move north.
shout  message='dragon spotted'  -> DRAGON SPOTTED

-- dispatch boundary (each failure named) --
  unknown tool         -> UnknownToolError: no tool registered as 'flee'
  undeclared arg       -> ToolArgumentError: tool 'move' got undeclared argument(s): heading
  missing arg          -> ToolArgumentError: tool 'move': missing a required argument: 'direction'
  handler bug          -> TypeError: unsupported operand type(s) for +: 'int' and 'str'
  incoherent tool      -> ValueError: tool 't': handler requires argument(s) message not declared in parameters
  (a handler bug surfaces as its own error, never relabeled as an argument fault)

-- assertions --
  ✓ 1 registered tool dispatches and returns its result
  ...
assertions passed (9) ✓
```

## Considerations

- The registry owns the tool table from the start, and `Context` never holds
  tools, so the whole tool lifecycle lives in one component.
- A handler bug and a bad call are different failures. The bind runs before the
  handler, so a `TypeError` inside the handler is its own bug and reaches the
  caller unchanged, while a malformed call is a `ToolArgumentError` the model
  can correct.
- Dispatch validates argument names and binding, not types. The schema does not
  carry type or required-ness yet, so a wrong-typed value still reaches the
  handler at this step.

## Run

From `week1_baseline/`:

```bash
bin/02_the_registry
```

or directly (this folder is a [`uv`](https://docs.astral.sh/uv/) project):

```bash
uv run examples/example.py
```
