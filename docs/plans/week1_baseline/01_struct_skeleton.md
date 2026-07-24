# Step 01 · Struct skeleton plan

## Goal

The core data structures the agent is built on: `Message` (one conversation
entry, made of typed content blocks), `Tool` (a callable capability), and
`Context` (the live conversation state). Plain data with validation at
construction: no behaviour beyond what the data itself requires.

## Deliverables

The step package carries step 00 forward and adds:

```
week1_baseline/agent/01_struct_skeleton/
├── pyproject.toml
├── README.md                 # written from the built step
├── boukensha/
│   ├── __init__.py
│   ├── config.py             # carried forward
│   ├── message.py            # Role, content blocks, Message
│   ├── tool.py               # Tool
│   ├── context.py            # Context
│   └── tasks/                # carried forward
├── examples/
│   └── example.py            # runnable smoke test
```

The launcher:

```
week1_baseline/bin/01_struct_skeleton
```

## Design

### `Role`: the allowed conversation roles

An enum, so the closed set is explicit and validated at construction rather
than an informal string convention.

| Value | Meaning |
|---|---|
| `user` | input from the user (or a task instruction) |
| `assistant` | a model response |
| `tool_result` | the output of a tool call, fed back to the model |

### Content blocks: one provider-neutral shape

Position: message content is always a sequence of our own typed blocks, and
plain text is normalized to a one-element sequence at construction. There is
no `str | list` dual typing.

| Block | Fields | Represents |
|---|---|---|
| `TextBlock` | `text` | plain text |
| `ToolUseBlock` | `id`, `name`, `input` | the model requesting a tool call |
| `ToolResultBlock` | `tool_use_id`, `content` | a tool's output, linked to the call |

Rationale:

- One dialect downstream: the agent loop, the logger, and context compaction
  all read a single shape. Pair-aware compaction, which must never separate a
  tool call from its result, becomes a walk over typed blocks instead of
  pattern matching on provider payloads.
- Translation confined to the edge: each backend converts neutral blocks to
  its wire format when building a request and back when parsing a response,
  exactly two symmetric points per provider. No other component inspects
  content types.
- History is provider independent: a conversation stores no provider's
  dialect, so the backend can change between turns without re-interpreting
  stored history.
- The simple case stays simple: `Message.user("look around")` produces one
  `TextBlock`, and callers never build block lists by hand for plain text.

All three block types are defined here because they are the message model
itself: the `tool_result` role already exists in this step, and defining half
the content model would reintroduce dual typing the moment tool traffic
appears.

### `Message`: one conversation entry

Frozen dataclass: `role: Role`, `content: tuple[Block, ...]`.

Tool linkage is enforced at construction. The violations below are data that
can never be valid, so they fail here instead of as a provider 400 at request
time:

| Invariant | Enforced at construction |
|---|---|
| a `tool_result` message carries its linkage | role `tool_result` ⇒ content is `ToolResultBlock`s, each with a non-empty `tool_use_id` |
| no other role carries tool-result content | role ≠ `tool_result` ⇒ no `ToolResultBlock` in content |
| tool calls only come from the model | `ToolUseBlock` appears only in `assistant` messages |
| content holds only typed blocks | every element is a `TextBlock`, `ToolUseBlock`, or `ToolResultBlock` |

The linkage lives in one place, `ToolResultBlock.tool_use_id`, not duplicated
as a message-level field, so the link between a call and its result cannot
drift into two disagreeing copies. A read-only `Message.tool_use_ids` property
exposes them as a tuple, plural because a message carries several results when
the model issued parallel tool calls. Constructor helpers:
`Message.user(text)`, `Message.assistant(blocks_or_text)`,
`Message.tool_result(tool_use_id, content)`.

### `Tool`: a callable capability

Frozen dataclass, a value object only: registration and dispatch are the next
component's job.

| Field | Type | Purpose |
|---|---|---|
| `name` | `str` | the name the model calls it by |
| `description` | `str` | what the model reads to decide when to use it |
| `parameters` | mapping | parameter name → its schema |
| `handler` | callable | the function that executes the tool |

### `Context`: the live conversation state

The one mutable holder, and all mutation goes through its methods.

| Holds | Method surface |
|---|---|
| system prompt | set at construction |
| ordered message history | `add(message)`: appends a validated `Message` |

Deliberately **not** in `Context` at this step:

- No tool table: tool ownership belongs to the registry component, introduced
  next. Storage is defined once in its owning component rather than placed
  here and relocated.
- No token accounting: added by the context-management component that uses
  it.
- No turn counter: turns are a concept of whoever runs the conversation, the
  REPL and the loop, and are derivable from the history Context already
  holds.

### Immutability rules

| Structure | Mutability | Why |
|---|---|---|
| blocks, `Message` | frozen, content stored as a tuple | a conversation entry never changes after creation |
| `Tool` | frozen | a tool definition never changes after registration |
| `Context` | mutable, via methods only | it *is* the evolving conversation state |

Accidental in-place edits of frozen structures fail loudly.

## Verification

```bash
bin/01_struct_skeleton      # from week1_baseline/; wraps:
uv run examples/example.py
```

The example builds messages, a tool, and a context, prints the resulting
state, and asserts:

| # | Assertion |
|---|---|
| 1 | an invalid role is rejected at construction |
| 2 | plain text normalizes to a one-element `TextBlock` sequence |
| 3 | a `tool_result` message without its linkage is rejected at construction |
| 4 | a non-`tool_result` message carrying tool-result content is rejected |
| 5 | a `Message` cannot be mutated after creation |
| 6 | `Context.add` preserves order and count |
| 7 | a `ToolUseBlock` outside an `assistant` message is rejected |
| 8 | a content element that is not a typed block is rejected |
| 9 | `Context.add` rejects a non-`Message` argument |

## Done when

The launcher runs the example successfully, all assertions pass, and the step
README is written from the built step.
