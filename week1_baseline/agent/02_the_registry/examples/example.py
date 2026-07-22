"""Smoke test for the tool registry.

Registers tools two ways, dispatches them, and asserts the ownership and
dispatch-boundary guarantees.
"""

from boukensha import (
    Config,
    Context,
    Registry,
    Tool,
    ToolArgumentError,
    UnknownToolError,
)

config = Config()
registry = Registry()


@registry.tool(
    "move",
    "Move the player in a direction.",
    {"direction": {"type": "string"}},
)
def move(direction):
    return f"You move {direction}."


registry.register(
    Tool(
        "shout",
        "Shout a message to the zone.",
        {"message": {"type": "string"}},
        lambda message: message.upper(),
    )
)


@registry.tool("boom", "A tool whose handler has an internal bug.", {})
def boom():
    return 1 + "not a number"  # raises TypeError inside the body

print("=== boukensha · step 02: the registry ===")
print()
print(f"Config:   {config}")
print(f"Registry: {registry}")
print(f"move -> {registry.dispatch('move', {'direction': 'north'})}")
print(f"shout -> {registry.dispatch('shout', {'message': 'dragon spotted'})}")


def rejected(call, error):
    try:
        call()
        return False
    except error:
        return True


def raised_type(call):
    try:
        call()
    except Exception as exc:
        return type(exc)
    return None


checks = {
    "1 registered tool dispatches and returns its result":
        registry.dispatch("shout", {"message": "hi"}) == "HI",
    "2 decorator registers and returns the function callable":
        callable(move) and move("west") == "You move west.",
    "3 unknown tool raises UnknownToolError":
        rejected(lambda: registry.dispatch("flee"), UnknownToolError),
    "4 duplicate name is rejected at registration":
        rejected(
            lambda: registry.register(Tool("move", "dup", {}, lambda: None)),
            ValueError,
        ),
    "5 undeclared argument raises ToolArgumentError":
        rejected(
            lambda: registry.dispatch("move", {"heading": "north"}),
            ToolArgumentError,
        ),
    "6 missing argument raises ToolArgumentError":
        rejected(lambda: registry.dispatch("move", {}), ToolArgumentError),
    "7 Context exposes no tool table":
        not hasattr(Context(), "tools") and not hasattr(Context(), "register_tool"),
    "8 handler's own TypeError propagates unrelabeled":
        raised_type(lambda: registry.dispatch("boom")) is TypeError,
    "9 schema that omits a required handler argument is rejected at build":
        rejected(lambda: Tool("t", "d", {}, lambda message: message), ValueError),
}

print()
for label, passed in checks.items():
    print(f"  {'✓' if passed else '✗'} {label}")
assert all(checks.values()), "one or more registry guarantees failed"
print()
print("assertions passed (9) ✓")
