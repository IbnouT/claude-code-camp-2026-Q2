"""Step 06: the logger.

The headline is a real turn with a logger attached. The agent explores a small
MUD world, and the logger records the turn to a JSONL session file. Running it
prints the final response and then the session log it wrote, phase by phase, so
a reader sees the ordered record on real data: iteration, prompt, response with
its token cost, the tool call and result, and the turn's end. It is gated behind
BOUKENSHA_LIVE=1 and needs the provider's key (see .boukensha/.env).

The offline block backs it. Loggers write to temporary directories or an
explicit path, agent runs replay provider-shaped JSON through a scripted
transport, so the phase ordering, the field serialization, the tool-error
capture, the cost accounting, and the default-directory safety are all checked
with no keys, network, or waiting.

Factual values and wire shapes, verified 2026-07-23:
- claude-haiku-4-5 per-million pricing (input 1.00, output 5.00 USD), so
  1000 input + 100 output tokens cost (1000*1 + 100*5)/1e6 = 0.0015 USD. Source,
  the bundled model catalog (boukensha/models.yaml), whose entries each cite a
  provider price page.
- Normalized token keys per provider:
  Anthropic Messages `usage.input_tokens/output_tokens`
    https://platform.claude.com/docs/en/api/messages
  OpenAI Responses `usage.input_tokens/output_tokens`
    https://developers.openai.com/api/reference/resources/responses
  Gemini `usageMetadata.promptTokenCount/candidatesTokenCount`
    https://ai.google.dev/api/generate-content
  Ollama `prompt_eval_count/eval_count`
    https://github.com/ollama/ollama/blob/main/docs/api.md
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from boukensha import (
    Agent,
    Client,
    Config,
    Context,
    Logger,
    Message,
    Player,
    PromptBuilder,
    Registry,
    TextBlock,
    Tool,
    ToolUseBlock,
    backend_for,
)

MODELS = {
    "anthropic": "claude-haiku-4-5",
    "gemini": "gemini-3.1-pro-preview",
    "ollama": "gpt-oss:20b",
    "ollama_cloud": "gpt-oss:120b",
}


def read_lines(path):
    """Every JSON object written to a session file, in order."""
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def find(lines, phase):
    return next(line for line in lines if line["phase"] == phase)


def render(line):
    """One session-log line as a compact human-readable string."""
    p = line["phase"]
    if p == "session_start":
        extra = " ".join(
            f"{k}={v}" for k, v in line.items()
            if k not in {"phase", "session_id", "at"}
        )
        return f"session_start{(' ' + extra) if extra else ''}"
    if p == "iteration":
        return f"iteration n={line['n']}/{line['max']}"
    if p == "limit_reached":
        return f"limit_reached {line['kind']} {line['n']}/{line['max']}"
    if p == "prompt":
        return f"prompt {line['message_count']} msgs, tools={line['tools']}"
    if p == "response":
        meta = []
        if "provider" in line:
            meta.append(f"{line.get('task')}/{line['provider']}/{line['model']}")
        if line.get("input_tokens") is not None:
            meta.append(f"{line['input_tokens']}+{line['output_tokens']} tok")
        if "cost_usd" in line:
            meta.append(f"${line['cost_usd']}")
        tail = ("  |  " + "  ".join(meta)) if meta else ""
        return f'response "{line["text"] or "(no text)"}"{tail}'
    if p == "tool_call":
        return f"tool_call {line['name']}({line['args']})"
    if p == "tool_result":
        flag = "ok" if line["ok"] else "ERROR"
        return f"tool_result {flag} {line['name']} -> {line['result'][:52]}"
    if p == "turn_end":
        return f"turn_end {line['reason']} after {line['iterations']} iter"
    if p == "raw":
        return f"raw keys={list(line['data'].keys())}"
    return p


# =========================================================================
# The real run: a real turn through a small MUD world, and the session log
# the logger wrote for it, phase by phase, on real tokens and cost.
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
        "Explore the world from where you stand, then give me a short map: each "
        "room and which rooms connect to it."))
    registry = mud_registry(state)
    builder = PromptBuilder(ctx, backend, tuple(registry.tools.values()))

    print("=== boukensha · step 06: the logger (real run) ===")
    print()
    print(f"Config:            {config}")
    print(f"Provider / model:  {provider} / {model}")
    print(f"Tools:             {', '.join(registry.tools)}")
    print()

    if os.environ.get("BOUKENSHA_LIVE") != "1":
        print("Real run gated: set BOUKENSHA_LIVE=1 (with the provider key in")
        print(".boukensha/.env) to record a real turn. The offline block runs below.")
        print()
        return
    if backend.api_key_env and not os.environ.get(backend.api_key_env):
        print(f"Real run skipped: BOUKENSHA_LIVE=1 is set but {backend.api_key_env} is not.")
        print("Add it to .boukensha/.env. The offline block runs below.")
        print()
        return

    # A live run logs where the real agent does: the default sessions dir
    # under the resolved .boukensha/ (git-ignored), so the turn leaves a
    # real session file you can open, tail, and grep after the run.
    logger = Logger(snapshot={"host": "localhost", "port": 4000})
    agent = Agent(ctx, registry, builder, Client(builder),
                  task=Player, task_settings=settings, logger=logger)

    print(f"Recording the turn to {logger.path}")
    print()
    final = agent.run()
    logger.close()
    print()
    print("=== final response ===")
    print(final)
    print()
    print(f"the session log it wrote, phase by phase ({logger.path.name}):")
    for line in read_lines(logger.path):
        print(f"  {render(line)}")
    print()


run_live()


# =========================================================================
# Offline invariants. Loggers write to a temp dir, agent runs replay scripted
# provider JSON. No key, network, or waiting.
# =========================================================================

TMP = Path(tempfile.mkdtemp(prefix="boukensha-step06-"))


class StubTransport:
    """Replays scripted steps in order; the last repeats if the script runs out."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step


def ok(payload):
    return (200, json.dumps(payload), {})


def anthropic_tool_use(*calls, text="Let me look."):
    content = [{"type": "text", "text": text}] if text else []
    for cid, name, args in calls:
        content.append({"type": "tool_use", "id": cid, "name": name, "input": args})
    return {"stop_reason": "tool_use", "content": content,
            "usage": {"input_tokens": 1000, "output_tokens": 100}}


def anthropic_end_turn(text="You are in a forest clearing."):
    content = [{"type": "text", "text": text}] if text else []
    return {"stop_reason": "end_turn", "content": content,
            "usage": {"input_tokens": 1200, "output_tokens": 80}}


def make_agent(*script, logger, max_iterations=None, tool_handler=None):
    """An Agent over a scripted transport, wired to the given logger."""
    ctx = Context(system="You are a MUD player agent.")
    ctx.add(Message.user("Scout the area."))
    handler = tool_handler or (lambda direction: f"You move {direction}.")
    registry = Registry()
    registry.register(Tool(
        "move", "Move the player in a direction.",
        {"direction": {"type": "string"}}, handler))
    builder = PromptBuilder(ctx, backend_for("anthropic", MODELS["anthropic"]),
                            tuple(registry.tools.values()))
    client = Client(builder, transport=StubTransport(*script), sleep=lambda _s: None)
    agent = Agent(ctx, registry, builder, client,
                  task=Player, max_iterations=max_iterations, logger=logger)
    return agent


def token_pair(usage, backend):
    lg = Logger(dir=TMP)
    lg.response(text="x", usage=usage, task=Player, backend=backend)
    line = find(read_lines(lg.path), "response")
    lg.close()
    return line.get("input_tokens"), line.get("output_tokens")


def parses_iso(value):
    try:
        datetime.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def boom(direction):
    raise RuntimeError("the exit is blocked")


haiku = backend_for("anthropic", MODELS["anthropic"])

# Path composition, session_start with the merged snapshot, and JSON validity.
log1 = Logger(dir=TMP, snapshot={"host": "localhost", "port": 4000})
sid1 = log1.session_id
log1.iteration(n=1, max=25)
log1.turn_end(reason="completed", iterations=1)
lines1 = read_lines(log1.path)
log1.close()
start1 = lines1[0]

# An explicit log= path is used verbatim, overriding dir composition.
explicit = TMP / "custom" / "run.jsonl"
log4 = Logger(dir=TMP, log=explicit)
log4.close()

# Method field serialization: iteration, limit_reached, turn_end.
log7 = Logger(dir=TMP)
log7.iteration(n=2, max=25)
log7.limit_reached(kind="max_iterations", n=25, max=25)
log7.turn_end(reason="max_iterations", iterations=25, tokens=1234)
lines7 = read_lines(log7.path)
log7.close()

# prompt serializes messages to block dicts and lists the registry tool names.
ctx8 = Context(system="sys")
ctx8.add(Message.user("hello"))
ctx8.add(Message.assistant((
    TextBlock("thinking"),
    ToolUseBlock("toolu_1", "move", {"direction": "north"}),
)))
ctx8.add(Message.tool_result("toolu_1", "move", "You move north."))
reg8 = Registry()
reg8.register(Tool("move", "d", {"direction": {"type": "string"}}, lambda direction: direction))
reg8.register(Tool("look", "d", {}, lambda: "a room"))
log8 = Logger(dir=TMP)
log8.prompt(messages=ctx8.messages, tools=reg8.tools)
prompt8 = find(read_lines(log8.path), "prompt")
log8.close()
serialized_roles = [m["role"] for m in prompt8["messages"]]
serialized_types = [b["type"] for m in prompt8["messages"] for b in m["content"]]

# tool_call, tool_result ok, and a raising tool captured ok=False.
log10 = Logger(dir=TMP)
log10.tool_call(name="move", args={"direction": "north"})
log10.tool_result(name="move", result="You move north.", ok=True)
try:
    raise RuntimeError("the exit is blocked")
except RuntimeError as exc:
    log10.tool_result(name="move", result=f"ERROR: {type(exc).__name__}: {exc}",
                      ok=False, error=str(exc))
lines10 = read_lines(log10.path)
log10.close()
call10 = find(lines10, "tool_call")
results10 = [line for line in lines10 if line["phase"] == "tool_result"]

# response metadata: a priced model computes cost; a null-price model omits it.
log12 = Logger(dir=TMP)
log12.response(text="  the door opens  ", stop_reason="end_turn",
               usage={"input_tokens": 1000, "output_tokens": 100},
               task=Player, backend=haiku)
resp12 = find(read_lines(log12.path), "response")
log12.close()
cloud = backend_for("ollama_cloud", MODELS["ollama_cloud"])  # cost_per_million null
log12_free = Logger(dir=TMP)
log12_free.response(text="x", usage={"prompt_eval_count": 500, "eval_count": 50},
                    task=Player, backend=cloud)
resp12_free = find(read_lines(log12_free.path), "response")
log12_free.close()

# usage_tokens across provider key shapes, plus missing/non-integer dropped.
gem = backend_for("gemini", MODELS["gemini"])
oll = backend_for("ollama", MODELS["ollama"])
pair_anthropic = token_pair({"input_tokens": 10, "output_tokens": 2}, haiku)
pair_gemini = token_pair({"promptTokenCount": 30, "candidatesTokenCount": 4}, gem)
pair_ollama = token_pair({"prompt_eval_count": 50, "eval_count": 6}, oll)
pair_openai = token_pair({"input_tokens": 70, "output_tokens": 8}, haiku)
pair_missing = token_pair({}, haiku)
pair_noninteger = token_pair({"input_tokens": "lots", "output_tokens": 8}, haiku)
pair_bool = token_pair({"input_tokens": True, "output_tokens": 8}, haiku)

# raw is gated on debug.
log15_off = Logger(dir=TMP, debug=False)
log15_off.raw(data={"anything": True})
lines15_off = read_lines(log15_off.path)
log15_off.close()
log15_on = Logger(dir=TMP, debug=True)
log15_on.raw(data={"stop_reason": "tool_use"})
lines15_on = read_lines(log15_on.path)
log15_on.close()

# A full stubbed run: the ordered phases, response before tool_call/result.
log16 = Logger(dir=TMP)
a16 = make_agent(
    ok(anthropic_tool_use(("toolu_1", "move", {"direction": "north"}))),
    ok(anthropic_end_turn()), logger=log16)
result16 = a16.run()
log16.close()
phases16 = [line["phase"] for line in read_lines(log16.path)]
final16 = find(read_lines(log16.path), "turn_end")

# A wind-down run: limit_reached, the wrap_up response, turn_end(max_iterations).
log17 = Logger(dir=TMP)
a17 = make_agent(
    ok(anthropic_tool_use(("toolu_1", "move", {"direction": "north"}))),
    ok(anthropic_end_turn("Wound down: mapped one room.")),
    logger=log17, max_iterations=1)
result17 = a17.run()
log17.close()
phases17 = [line["phase"] for line in read_lines(log17.path)]
after_limit17 = phases17[phases17.index("limit_reached"):][:3]
limit17 = find(read_lines(log17.path), "limit_reached")
turn_end17 = find(read_lines(log17.path), "turn_end")

# A raising tool in a full run is captured ok=False and the turn continues.
log11b = Logger(dir=TMP)
a11b = make_agent(
    ok(anthropic_tool_use(("toolu_1", "move", {"direction": "north"}))),
    ok(anthropic_end_turn("Recovered.")), logger=log11b, tool_handler=boom)
result11b = a11b.run()
log11b.close()
tool_result11b = find(read_lines(log11b.path), "tool_result")

# The default directory resolves under Config's dir, never the repo.
prev_dir = os.environ.get("BOUKENSHA_DIR")
env_tmp = Path(tempfile.mkdtemp(prefix="boukensha-step06-env-"))
os.environ["BOUKENSHA_DIR"] = str(env_tmp)
log18 = Logger()
default_parent = log18.path.parent
log18.close()
if prev_dir is None:
    del os.environ["BOUKENSHA_DIR"]
else:
    os.environ["BOUKENSHA_DIR"] = prev_dir

# A value that fails to serialize is recorded, not raised: the turn survives.
class _Unserializable:
    def __str__(self):
        raise RuntimeError("boom")
    __repr__ = __str__


log_resilient = Logger(dir=TMP)
log_resilient.tool_call(name="move", args={"bad": _Unserializable()})
log_resilient.tool_result(name="move", result="ok")
resilient_lines = read_lines(log_resilient.path)
log_resilient.close()

# Tool-call ids pair a call to its result through a full agent run.
tool_call16 = find(read_lines(log16.path), "tool_call")
tool_result16 = find(read_lines(log16.path), "tool_result")

# Response duration, per-turn totals, and retry logging over full agent runs.
logB4 = Logger(dir=TMP)
make_agent(ok(anthropic_end_turn()), logger=logB4).run()
linesB4 = read_lines(logB4.path)
logB4.close()
respB4 = find(linesB4, "response")
endB4 = find(linesB4, "turn_end")

logB4r = Logger(dir=TMP)
make_agent((429, json.dumps({}), {}), ok(anthropic_end_turn()), logger=logB4r).run()
linesB4r = read_lines(logB4r.path)
logB4r.close()
retriesB4 = [line for line in linesB4r if line["phase"] == "retry"]


checks = {
    "dir composes <dir>/<session_id>.jsonl; session_start carries the schema and snapshot; every line is JSON with session_id and an ISO at":
        log1.path == TMP / f"{sid1}.jsonl" and log1.path.exists()
        and start1["phase"] == "session_start" and start1["session_id"] == sid1
        and start1["schema"] == 1
        and start1["host"] == "localhost" and start1["port"] == 4000
        and len(lines1) == 3
        and all("session_id" in line and parses_iso(line["at"]) for line in lines1),
    "an explicit log= path is used verbatim, overriding dir composition":
        log4.path == explicit and explicit.exists(),
    "iteration, limit_reached, and turn_end write their phase and fields":
        find(lines7, "iteration")["n"] == 2 and find(lines7, "iteration")["max"] == 25
        and find(lines7, "limit_reached")["kind"] == "max_iterations"
        and find(lines7, "turn_end")["reason"] == "max_iterations"
        and find(lines7, "turn_end")["iterations"] == 25
        and find(lines7, "turn_end")["tokens"] == 1234,
    "prompt writes message_count, tool_count, tool names, and messages serialized to block dicts":
        prompt8["message_count"] == 3 and prompt8["tool_count"] == 2
        and prompt8["tools"] == ["move", "look"]
        and serialized_roles == ["user", "assistant", "tool_result"]
        and serialized_types == ["text", "text", "tool_use", "tool_result"]
        and prompt8["messages"][1]["content"][1]
        == {"type": "tool_use", "id": "toolu_1", "name": "move",
            "input": {"direction": "north"}}
        and prompt8["messages"][2]["content"][0]
        == {"type": "tool_result", "tool_use_id": "toolu_1",
            "tool_name": "move", "content": "You move north."},
    "tool_call logs name and args; tool_result logs the result with ok=True; a raising tool yields ok=False, the error, and an ERROR: result":
        call10["name"] == "move" and call10["args"] == {"direction": "north"}
        and results10[0]["result"] == "You move north." and results10[0]["ok"] is True
        and results10[1]["ok"] is False and results10[1]["error"] == "the exit is blocked"
        and results10[1]["result"].startswith("ERROR:")
        and tool_result11b["ok"] is False
        and tool_result11b["result"].startswith("ERROR: RuntimeError:")
        and result11b == "Recovered.",
    "response writes stripped text, usage, a metadata block, and cost for a priced model; a null-price model omits cost and marks subscription":
        resp12["text"] == "the door opens" and resp12["stop_reason"] == "end_turn"
        and resp12["usage"] == {"input_tokens": 1000, "output_tokens": 100}
        and resp12["task"] == "player" and resp12["provider"] == "anthropic"
        and resp12["model"] == "claude-haiku-4-5" and resp12["usage_unit"] == "tokens"
        and resp12["input_tokens"] == 1000 and resp12["output_tokens"] == 100
        and resp12["cost_usd"] == (1000 * 1.00 + 100 * 5.00) / 1e6
        and isinstance(resp12["context_window"], int) and resp12["context_window"] > 0
        and "cost_usd" not in resp12_free and resp12_free["usage_unit"] == "subscription",
    "usage tokens are picked across each provider's key names; missing, non-integer, or bool counts drop to None":
        pair_anthropic == (10, 2) and pair_gemini == (30, 4)
        and pair_ollama == (50, 6) and pair_openai == (70, 8)
        and pair_missing == (None, None) and pair_noninteger == (None, 8)
        and pair_bool == (None, 8),
    "raw writes nothing when debug is off and one raw line with its data when debug is on":
        [line["phase"] for line in lines15_off] == ["session_start"]
        and find(lines15_on, "raw")["data"] == {"stop_reason": "tool_use"},
    "a full run writes the ordered phases, response before tool_call/tool_result, ending completed":
        phases16 == ["session_start", "iteration", "prompt", "response",
                     "tool_call", "tool_result", "iteration", "prompt",
                     "response", "turn_end"]
        and final16["reason"] == "completed"
        and result16 == "You are in a forest clearing.",
    "a wind-down writes limit_reached (with its kind), then the wrap_up response, then turn_end(max_iterations)":
        after_limit17 == ["limit_reached", "response", "turn_end"]
        and limit17["kind"] == "max_iterations"
        and turn_end17["reason"] == "max_iterations"
        and result17 == "Wound down: mapped one room.",
    "the default directory resolves to Config's dir/sessions, never the repo":
        default_parent == env_tmp.resolve() / "sessions"
        and "camp" not in str(default_parent),
    "a tool_use id pairs a tool_call to its tool_result through a full run":
        tool_call16.get("id") == "toolu_1"
        and tool_result16.get("tool_use_id") == "toolu_1",
    "a value that fails to serialize is recorded as log_error, and the logger keeps working":
        any(line["phase"] == "log_error" and line["original_phase"] == "tool_call"
            for line in resilient_lines)
        and any(line["phase"] == "tool_result" for line in resilient_lines),
    "response carries an integer duration_ms; turn_end carries the turn's summed input/output tokens, cost, and duration":
        isinstance(respB4.get("duration_ms"), int) and respB4["duration_ms"] >= 0
        and endB4.get("input_tokens") == 1200 and endB4.get("output_tokens") == 80
        and endB4.get("cost_usd") == (1200 * 1.00 + 80 * 5.00) / 1e6
        and isinstance(endB4.get("duration_ms"), int),
    "a retryable status is recorded as a retry event (attempt, wait, status) before the successful reply":
        len(retriesB4) == 1 and retriesB4[0]["status"] == 429
        and retriesB4[0]["attempt"] == 1 and isinstance(retriesB4[0]["wait"], (int, float)),
    "PHASES lists every phase the logger emits, retry and turn_end included":
        {"retry", "turn_end", "response", "reasoning", "plan"}.issubset(set(Logger.PHASES)),
}

print("-- offline invariants (no key, scripted transport) --")
for label, passed in checks.items():
    print(f"  {'PASS' if passed else 'FAIL'} {label}")
assert all(checks.values()), "one or more logger invariants failed"
