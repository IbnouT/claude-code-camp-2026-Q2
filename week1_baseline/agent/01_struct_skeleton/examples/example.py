"""Smoke test for the data structures.

Builds messages, a tool, and a context, prints the state, and asserts the
construction invariants that keep invalid conversation data out of a request.
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

config = Config()
system_prompt = Player.system_prompt(
    config.tasks("player"), config.user_prompt_path(Player.task_name)
)

ctx = Context(system=system_prompt)
ctx.add(Message.user("Explore north and tell me what you find."))
ctx.add(Message.assistant("Heading north to look around."))
ctx.add(Message.assistant(ToolUseBlock("call_1", "move", {"direction": "north"})))
ctx.add(Message.tool_result("call_1", "You move north into a torch-lit corridor."))

move = Tool(
    "move",
    "Move the player in a direction.",
    {"direction": {"type": "string", "description": "The direction to move"}},
    lambda direction: f"You move {direction}.",
)

print("=== boukensha · step 01: struct skeleton ===")
print()
print(f"Config:   {config}")
print(f"Context:  {ctx}")
print(f"Tool:     {move}")
print("Messages:")
for m in ctx.messages:
    print(f"  {m}  tool_use_ids={m.tool_use_ids}")


def rejected(build) -> bool:
    """True if construction raised, i.e. the invariant held."""
    try:
        build()
        return False
    except (ValueError, TypeError):
        return True


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
    "1 invalid role rejected":
        rejected(lambda: Message("user", "hi")),
    "2 text normalizes to one TextBlock":
        Message.user("look").content == (TextBlock("look"),),
    "3 tool_result without linkage rejected":
        rejected(lambda: Message(Role.TOOL_RESULT, ToolResultBlock("", "out"))),
    "4 tool-result content on other role rejected":
        rejected(lambda: Message(Role.USER, ToolResultBlock("call_1", "out"))),
    "5 message is immutable":
        is_frozen(Message.user("look")),
    "6 add preserves order and count":
        [b.text for msg in order_ctx.messages for b in msg.content] == ["a", "b"],
    "7 tool_use outside assistant rejected":
        rejected(lambda: Message(Role.USER, ToolUseBlock("id", "move", {}))),
    "8 untyped content element rejected":
        rejected(lambda: Message(Role.USER, ["not a block"])),
    "9 Context.add rejects a non-Message":
        rejected(lambda: Context().add("not a message")),
}

print()
for label, passed in checks.items():
    print(f"  {'✓' if passed else '✗'} {label}")
assert all(checks.values()), "one or more invariants failed"
print()
print("assertions passed (9) ✓")
