"""Demonstration of the tool registry.

Runs entirely offline. It registers tools two ways, dispatches them, then walks
the dispatch boundary so each failure the model can cause prints as a named
error. The compact assertion pass at the end pins the same behavior.
"""

from boukensha import (
    Config,
    Context,
    Registry,
    Tool,
    ToolArgumentError,
    UnknownToolError,
)

# -- register tools --------------------------------------------------------

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

print("=== boukensha · step 02: the registry ===")
print()
print(f"Config:   {config}")
print()
print("-- registered tools --")
print(f"Registry: {registry}")
for tool in registry.tools.values():
    print(f"  {tool}")

# -- dispatch (the model emits a name and args, the registry runs it) -------

print()
print("-- dispatch --")
print(f"move   direction='north'         -> {registry.dispatch('move', {'direction': 'north'})}")
print(f"shout  message='dragon spotted'  -> {registry.dispatch('shout', {'message': 'dragon spotted'})}")


# -- dispatch boundary (every failure the model can cause is named) ---------


@registry.tool("boom", "A tool whose handler has an internal bug.", {})
def boom():
    return 1 + "not a number"  # raises TypeError inside the body


def show(label, call):
    """Run a call expected to fail and print the error it raised."""
    try:
        call()
    except Exception as exc:
        print(f"  {label:<20} -> {type(exc).__name__}: {exc}")


print()
print("-- dispatch boundary (each failure named) --")
show("unknown tool", lambda: registry.dispatch("flee"))
show("undeclared arg", lambda: registry.dispatch("move", {"heading": "north"}))
show("missing arg", lambda: registry.dispatch("move", {}))
show("handler bug", lambda: registry.dispatch("boom"))
show("incoherent tool", lambda: Tool("t", "d", {}, lambda message: message))
print("  (a handler bug surfaces as its own error, never relabeled as an argument fault)")


# -- assertions ------------------------------------------------------------


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
print("-- assertions --")
for label, passed in checks.items():
    print(f"  {'✓' if passed else '✗'} {label}")
assert all(checks.values()), "one or more registry guarantees failed"
print()
print("assertions passed (9) ✓")
