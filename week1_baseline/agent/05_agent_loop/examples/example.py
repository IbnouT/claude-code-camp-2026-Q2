"""Step 05: the agent loop.

The headline is a real turn. The agent is handed two MUD tools and a goal, and
``run()`` drives the loop live against the configured provider: the model looks
around, moves, reads each result, and iterates until it can answer. Running this
is the demonstration, and it needs the provider's API key (see .boukensha/.env).
Local Ollama needs none. Without a key the real run is skipped with a notice and
the offline block below still runs.

That offline block drives the same loop over a scripted transport to pin down
the invariants a single live run cannot guarantee on its own: the tool_result
wiring, the wind-down at max_iterations, and cross-provider response parsing. It
needs no key, network, or waiting.
"""

import io
import json
import os
from contextlib import redirect_stdout

from boukensha import (
    Agent,
    Client,
    Config,
    Context,
    LoopError,
    Message,
    Player,
    PromptBuilder,
    Registry,
    Role,
    Tool,
    ToolResultBlock,
    ToolUseBlock,
    backend_for,
)
from boukensha.backends import Ollama, OllamaCloud

# =========================================================================
# The real run: a small MUD world, two tools, and the loop end to end. The
# world is a fixture, the model's choices and the loop that dispatches them
# are live.
# =========================================================================

WORLD = {
    "clearing": ("A sunlit forest clearing. A path leads north and a stream runs east.",
                 {"north": "grove", "east": "brook"}),
    "grove": ("A mossy grove ringed with standing stones. The path goes on north, or back south.",
              {"north": "cave", "south": "clearing"}),
    "brook": ("A shallow brook chatters over pebbles. The only way is back west.",
              {"west": "clearing"}),
    "cave": ("A dark cave mouth breathes cold air. The way south returns to the grove.",
             {"south": "grove"}),
}


def _describe(room):
    desc, exits = WORLD[room]
    return f"{desc} Exits: {', '.join(exits)}."


def _move(state, direction):
    _desc, exits = WORLD[state["room"]]
    if direction not in exits:
        return f"You cannot go {direction} from here. Exits: {', '.join(exits)}."
    state["room"] = exits[direction]
    return _describe(state["room"])


def mud_registry(state):
    """Two tools over the WORLD fixture: look at the room, move through an exit."""
    registry = Registry()
    registry.register(Tool(
        "look", "Describe the current room and its exits.", {},
        lambda: _describe(state["room"]),
    ))
    registry.register(Tool(
        "move", "Move through an exit, for example north.",
        {"direction": {"type": "string", "description": "Which exit to take."}},
        lambda direction: _move(state, direction),
    ))
    return registry


def run_live():
    config = Config()
    settings = config.tasks("player")
    provider = Player.provider(settings)
    model = Player.model(settings)
    backend = backend_for(provider, model)

    state = {"room": "clearing"}
    ctx = Context(system="You are a MUD player agent. Use look and move to explore, then report.")
    ctx.add(Message.user(
        "Explore the world from where you stand. Visit every room you can reach, "
        "then give me a short map: each room and which rooms connect to it."))
    registry = mud_registry(state)
    builder = PromptBuilder(ctx, backend, tuple(registry.tools.values()))
    agent = Agent(ctx, registry, builder, Client(builder),
                  task=Player, task_settings=settings)

    print("=== boukensha · step 05: agent loop (real run) ===")
    print()
    print(f"Config:            {config}")
    print(f"Provider / model:  {provider} / {model}")
    print(f"Max iterations:    {Player.max_iterations(settings)}")
    print(f"Tools:             {', '.join(registry.tools)}")
    print(f"Start room:        {state['room']}")
    print()

    if os.environ.get("BOUKENSHA_LIVE") != "1":
        print("Real run gated: set BOUKENSHA_LIVE=1 (with the provider key in")
        print(".boukensha/.env) to watch the model drive the loop live. Offline block below.")
        print()
        return
    if backend.api_key_env and not os.environ.get(backend.api_key_env):
        print(f"Real run skipped: BOUKENSHA_LIVE=1 is set but {backend.api_key_env} is not.")
        print("Add it to .boukensha/.env. The offline block runs below.")
        print()
        return

    print("Running the loop live. The model calls tools and iterates until done:")
    print()
    final = agent.run()
    print()
    print("=== final response ===")
    print(final)
    print()


run_live()


# =========================================================================
# Offline invariants. The same loop over a scripted transport, no key needed.
# Each scenario's own iteration prints are silenced so only the results show.
# =========================================================================

MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-5.4",
    "gemini": "gemini-3.1-pro-preview",
    "ollama": "gpt-oss:20b",
    "ollama_cloud": "gpt-oss:120b",
}


class StubTransport:
    """Replays scripted (status, body, headers) steps in order; the last repeats."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]


def ok(payload):
    return (200, json.dumps(payload), {})


def tool_use(*calls, text="Let me look."):
    content = [{"type": "text", "text": text}] if text else []
    for cid, name, args in calls:
        content.append({"type": "tool_use", "id": cid, "name": name, "input": args})
    return {"stop_reason": "tool_use", "content": content}


def end_turn(text="You are back in the clearing."):
    return {"stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}] if text else []}


def scripted_agent(*script, max_iterations=None, task_settings=None):
    """An Agent whose model replies are the given script; records moves dispatched."""
    moves = []
    ctx = Context(system="You are a MUD player agent.")
    ctx.add(Message.user("Scout the area."))
    registry = Registry()
    registry.register(Tool(
        "move", "Move in a direction.", {"direction": {"type": "string"}},
        lambda direction: moves.append(direction) or f"You move {direction}.",
    ))
    builder = PromptBuilder(ctx, backend_for("anthropic", MODELS["anthropic"]),
                            tuple(registry.tools.values()))
    transport = StubTransport(*script)
    agent = Agent(ctx, registry, builder,
                  Client(builder, transport=transport, sleep=lambda _s: None),
                  task=Player, task_settings=task_settings or {},
                  max_iterations=max_iterations)
    return agent, ctx, transport, moves


with redirect_stdout(io.StringIO()):
    # One tool call, then a final answer.
    a1, ctx1, t1, moves1 = scripted_agent(
        ok(tool_use(("t1", "move", {"direction": "north"}))), ok(end_turn()))
    result1 = a1.run()

    # Two tool_use blocks in one reply, both dispatched before the next call.
    a2, ctx2, t2, moves2 = scripted_agent(
        ok(tool_use(("ta", "move", {"direction": "north"}),
                    ("tb", "move", {"direction": "south"}))), ok(end_turn()))
    a2.run()

    # Reaching max_iterations winds down once, with tools disabled.
    a3, ctx3, t3, moves3 = scripted_agent(
        ok(tool_use(("t1", "move", {"direction": "north"}))),
        ok(tool_use(("t2", "move", {"direction": "north"}))),
        ok(end_turn("Wound down: mapped two rooms.")), max_iterations=2)
    result3 = a3.run()
    winddown_body = json.loads(t3.calls[2][2])

    # A wind-down whose reply is empty falls back to a message naming the limit.
    a4, _c4, _t4, _m4 = scripted_agent(
        ok(tool_use(("t1", "move", {"direction": "north"}))),
        ok(end_turn(text="")), max_iterations=1)
    result4 = a4.run()

    # The iteration limit resolves explicit over task setting over the default.
    a_lim_x, *_ = scripted_agent(ok(end_turn()), max_iterations=7,
                                 task_settings={"max_iterations": 9})
    a_lim_t, *_ = scripted_agent(ok(end_turn()), task_settings={"max_iterations": 9})
    a_lim_d, *_ = scripted_agent(ok(end_turn()))

    # A task thinking level rides the loop's call into the request body; unset
    # sends no thinking field. The default model is a budget-thinking model, so
    # the level lands as an enabled block with budget_tokens < max_tokens.
    a_think, _ct, t_think, _mt = scripted_agent(
        ok(end_turn()), task_settings={"thinking": "high"})
    a_think.run()
    thinking_body = json.loads(t_think.calls[0][2])
    a_nothink, _cn, t_nothink, _mn = scripted_agent(ok(end_turn()))
    a_nothink.run()
    no_thinking_body = json.loads(t_nothink.calls[0][2])

    # Every backend normalizes its own tool-call shape into a ToolUseBlock.
    parsed = {}
    parsed["anthropic"] = backend_for("anthropic", MODELS["anthropic"]).parse_response(
        tool_use(("t9", "move", {"direction": "east"})))
    parsed["openai"] = backend_for("openai", MODELS["openai"]).parse_response({
        "output": [{"type": "function_call", "call_id": "c1", "name": "move",
                    "arguments": '{"direction": "east"}'}]})
    parsed["gemini"] = backend_for("gemini", MODELS["gemini"]).parse_response({
        "candidates": [{"content": {"parts": [
            {"functionCall": {"name": "move", "args": {"direction": "west"}}}]}}]})
    ollama_body = {"message": {"content": "ok", "tool_calls": [
        {"function": {"name": "move", "arguments": {"direction": "up"}}}]}}
    parsed["ollama"] = backend_for("ollama", MODELS["ollama"]).parse_response(ollama_body)
    parsed["ollama_cloud"] = backend_for(
        "ollama_cloud", MODELS["ollama_cloud"]).parse_response(ollama_body)


def only_tool_use(p):
    return [b for b in p.content if isinstance(b, ToolUseBlock)]


checks = {
    "a tool_use reply then end_turn dispatches the tool and returns the final text":
        moves1 == ["north"] and result1 == "You are back in the clearing."
        and len(t1.calls) == 2,
    "after a tool call the history is user, assistant (tool_use), tool_result carrying the call's id and name":
        [m.role for m in ctx1.messages] == [Role.USER, Role.ASSISTANT, Role.TOOL_RESULT]
        and isinstance(ctx1.messages[2].content[0], ToolResultBlock)
        and ctx1.messages[2].content[0].tool_use_id == "t1"
        and ctx1.messages[2].content[0].tool_name == "move",
    "two tool_use blocks in one reply are both dispatched before the next call":
        moves2 == ["north", "south"] and len(t2.calls) == 2,
    "reaching max_iterations winds down once with tools disabled and returns its text":
        result3 == "Wound down: mapped two rooms." and len(t3.calls) == 3
        and "tools" not in winddown_body and moves3 == ["north", "north"],
    "an empty wind-down reply falls back to a message naming the limit":
        "max_iterations" in result4,
    "every backend normalizes its tool call into a ToolUseBlock named move":
        all(only_tool_use(p) and only_tool_use(p)[0].name == "move"
            for p in parsed.values())
        and OllamaCloud.parse_response is Ollama.parse_response,
    "the constructor resolves the iteration limit explicit over task setting over default (25)":
        a_lim_x._max_iterations == 7 and a_lim_t._max_iterations == 9
        and a_lim_d._max_iterations == 25,
    "a task thinking level reaches the request body as a provider-valid block (budget < max_tokens); unset sends none":
        thinking_body.get("thinking") == {"type": "enabled", "budget_tokens": 16384}
        and thinking_body["thinking"]["budget_tokens"] < thinking_body["max_tokens"]
        and thinking_body["max_tokens"] == 16384 + 1024
        and "thinking" not in no_thinking_body,
    "LoopError is exported from the package root and is an Exception":
        issubclass(LoopError, Exception),
}

print("-- offline invariants (no key, scripted transport) --")
for label, passed in checks.items():
    print(f"  {'PASS' if passed else 'FAIL'} {label}")
assert all(checks.values()), "an agent-loop invariant failed"
