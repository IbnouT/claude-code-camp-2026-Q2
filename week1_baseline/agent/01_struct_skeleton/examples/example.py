"""Demonstration of the core data structures.

Runs entirely offline. It builds a small conversation, prints it, then shows
each construction invariant rejecting bad data with the error it raises. The
compact assertion pass at the end pins the same behavior.
"""

from dataclasses import FrozenInstanceError

from boukensha import (
    Config,
    Context,
    Message,
    Player,
    Role,
    TextBlock,
    Tool,
    ToolResultBlock,
    ToolUseBlock,
)

# -- build a conversation --------------------------------------------------

config = Config()
system_prompt = Player.system_prompt(
    config.tasks("player"), config.user_prompt_path(Player.task_name)
)

move = Tool(
    "move",
    "Move the player in a direction.",
    {"direction": {"type": "string", "description": "The direction to move"}},
    lambda direction: f"You move {direction}.",
)

ctx = Context(system=system_prompt)
ctx.add(Message.user("Explore north and tell me what you find."))
ctx.add(Message.assistant("Heading north to look around."))
ctx.add(Message.assistant(ToolUseBlock("call_1", "move", {"direction": "north"})))
ctx.add(Message.tool_result("call_1", "You move north into a torch-lit corridor."))

print("=== boukensha · step 01: struct skeleton ===")
print()
print(f"Config:   {config}")
print()
print("-- conversation --")
print(f"Context:  {ctx}")
print(f"Tool:     {move}")
print("Messages:")
for m in ctx.messages:
    print(f"  {m}  tool_use_ids={m.tool_use_ids}")

# -- invariants: bad data must fail at construction, not at request time ---

INVALID = [
    ("invalid role",
        lambda: Message("user", "hi")),
    ("tool_result without linkage",
        lambda: Message(Role.TOOL_RESULT, ToolResultBlock("", "out"))),
    ("tool result on another role",
        lambda: Message(Role.USER, ToolResultBlock("call_1", "out"))),
    ("tool call outside assistant",
        lambda: Message(Role.USER, ToolUseBlock("id", "move", {}))),
    ("untyped content element",
        lambda: Message(Role.USER, ["not a block"])),
    ("Context.add non-Message",
        lambda: Context().add("not a message")),
]


def rejection(build) -> str | None:
    """Return the error a failing construction raises, or None if it wrongly succeeded."""
    try:
        build()
        return None
    except (ValueError, TypeError) as exc:
        return str(exc)


rejections = {label: rejection(build) for label, build in INVALID}

print()
print("-- invariants (bad data rejected at construction) --")
for label, msg in rejections.items():
    mark = "✓" if msg else "✗"
    shown = f"rejected: {msg}" if msg else "NOT REJECTED"
    print(f"  {mark} {label:<29} {shown}")

# -- assertions ------------------------------------------------------------


def is_frozen(message) -> bool:
    try:
        message.role = Role.ASSISTANT
        return False
    except FrozenInstanceError:
        return True


order_ctx = Context()
order_ctx.add(Message.user("a"))
order_ctx.add(Message.user("b"))

checks = {
    "text normalizes to one TextBlock":
        Message.user("look").content == (TextBlock("look"),),
    "message is immutable":
        is_frozen(Message.user("look")),
    "add preserves order and count":
        [b.text for msg in order_ctx.messages for b in msg.content] == ["a", "b"],
    **{label: msg is not None for label, msg in rejections.items()},
}

assert all(checks.values()), f"failed: {[k for k, v in checks.items() if not v]}"
print()
print(f"assertions passed ({len(checks)}) ✓")
