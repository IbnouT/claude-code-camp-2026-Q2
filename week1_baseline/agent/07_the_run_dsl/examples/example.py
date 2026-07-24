"""Step 07: the run DSL.

The headline is a real run. One `run(task=..., setup=...)` call resolves config,
wires the whole chain (Context, Registry, backend, PromptBuilder, Client, Logger,
Agent), seeds the task, drives one turn live against the configured provider, and
returns the final text. Running it is the demonstration, and it needs the
provider's key (see .boukensha/.env). Gated behind BOUKENSHA_LIVE=1; the session
is logged under the real .boukensha/sessions/.

The offline block backs it. Each scenario drives `run` over a scripted transport
and an explicit temp `log=`, so the config resolution, the inline tool
registration through `RunDSL`, the override plumbing, the seeded task, and the
error path are checked with no key, network, or waiting.
"""

import json
import os
import tempfile
from pathlib import Path

# Pin the config directory before importing run, so Config() inside it resolves
# the repo's settings.yaml no matter where the launcher cd'd.
REPO_BOUKENSHA = Path(__file__).resolve().parents[4] / ".boukensha"
os.environ["BOUKENSHA_DIR"] = str(REPO_BOUKENSHA)

from boukensha import Config, Player, backend_for, run  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="boukensha-step07-"))


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def find(lines, phase):
    return next(line for line in lines if line["phase"] == phase)


# =========================================================================
# The real run: a small MUD world and one run() call that drives the loop.
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


def mud_setup(state):
    def setup(dsl):
        @dsl.tool("look", description="Describe the current room and its exits.",
                  parameters={})
        def look():
            return _describe(state["room"])

        @dsl.tool("move", description="Move through an exit, for example north.",
                  parameters={"direction": {"type": "string",
                                            "description": "Which exit to take."}})
        def move(direction):
            return _move(state, direction)
    return setup


def run_live():
    config = Config()
    settings = config.tasks("player")
    provider = Player.provider(settings)
    model = Player.model(settings)
    backend = backend_for(provider, model)

    print("=== boukensha · step 07: the run DSL (real run) ===")
    print()
    print(f"Config:            {config}")
    print(f"Provider / model:  {provider} / {model}")
    print()

    if os.environ.get("BOUKENSHA_LIVE") != "1":
        print("Real run gated: set BOUKENSHA_LIVE=1 (with the provider key in")
        print(".boukensha/.env) to drive a real turn. The offline block runs below.")
        print()
        return
    if backend.api_key_env and not os.environ.get(backend.api_key_env):
        print(f"Real run skipped: BOUKENSHA_LIVE=1 is set but {backend.api_key_env} is not.")
        print("Add it to .boukensha/.env. The offline block runs below.")
        print()
        return

    state = {"room": "clearing"}
    print("One run() call wires the whole chain and drives the turn live:")
    print()
    result = run(
        task="Explore the world from where you stand, then give me a short map: "
             "each room and which rooms connect to it.",
        setup=mud_setup(state),
    )
    print("=== final response ===")
    print(result)
    print()
    print("The turn was logged under .boukensha/sessions/.")
    print()


run_live()


# =========================================================================
# Offline invariants. Each run drives a scripted transport and a temp log=.
# No key, network, or waiting.
# =========================================================================

class StubTransport:
    """Replays scripted steps in order; the last repeats if the script runs out."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]


def ok(payload):
    return (200, json.dumps(payload), {})


def anthropic_tool_use(cid, name, args, text="Let me look."):
    content = [{"type": "text", "text": text}] if text else []
    content.append({"type": "tool_use", "id": cid, "name": name, "input": args})
    return {"stop_reason": "tool_use", "content": content,
            "usage": {"input_tokens": 1000, "output_tokens": 100}}


def anthropic_end_turn(text="You are in a forest clearing."):
    return {"stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 1200, "output_tokens": 80}}


def ollama_end_turn(text="A quiet clearing."):
    return {"message": {"role": "assistant", "content": text},
            "prompt_eval_count": 20, "eval_count": 6}


def move_setup(dsl):
    @dsl.tool("move", description="Move the player in a direction.",
              parameters={"direction": {"type": "string"}})
    def move(direction):
        return f"You move {direction}."


def temp_log(name):
    return str(TMP / name)


# One full run: config resolved, chain wired, one tool call, then a final answer.
log1 = temp_log("run1.jsonl")
result1 = run(task="Scout the area.", setup=move_setup, log=log1,
              transport=StubTransport(
                  ok(anthropic_tool_use("t1", "move", {"direction": "north"})),
                  ok(anthropic_end_turn())),
              sleep=lambda _s: None)
lines1 = read_lines(log1)
phases1 = [line["phase"] for line in lines1]
prompt1 = find(lines1, "prompt")
snap1 = lines1[0]

# Two inline tools become the registry tools, exactly, on the prompt line.
def two_tools(dsl):
    @dsl.tool("read_file", description="Read a file",
              parameters={"path": {"type": "string"}})
    def read_file(path):
        return "contents"

    @dsl.tool("list_dir", description="List a directory",
              parameters={"path": {"type": "string"}})
    def list_dir(path):
        return "a, b"


log2 = temp_log("run2.jsonl")
run(task="Do nothing.", setup=two_tools, log=log2,
    transport=StubTransport(ok(anthropic_end_turn())), sleep=lambda _s: None)
prompt2 = find(read_lines(log2), "prompt")

# The RunDSL exposes only tool.
captured = {}
run(task="x", setup=lambda dsl: captured.__setitem__("dsl", dsl),
    log=temp_log("run3.jsonl"),
    transport=StubTransport(ok(anthropic_end_turn())), sleep=lambda _s: None)
public_attrs = [a for a in dir(captured["dsl"]) if not a.startswith("_")]

# Explicit model, backend, max_iterations, and max_output_tokens override.
log4 = temp_log("run4.jsonl")
run(task="Look around.", model="gpt-oss:20b", backend="ollama",
    max_iterations=7, max_output_tokens=64, log=log4,
    transport=StubTransport(ok(ollama_end_turn())), sleep=lambda _s: None)
snap4 = read_lines(log4)[0]

# An unknown backend raises, naming the provider.
error5 = None
try:
    run(task="x", backend="nope", log=temp_log("run5.jsonl"),
        transport=StubTransport(ok(anthropic_end_turn())), sleep=lambda _s: None)
except ValueError as exc:
    error5 = str(exc)

# setup=None runs a turn with zero tools.
log6 = temp_log("run6.jsonl")
result6 = run(task="Just talk.", setup=None, log=log6,
              transport=StubTransport(ok(anthropic_end_turn("hello"))),
              sleep=lambda _s: None)
prompt6 = find(read_lines(log6), "prompt")

# A thinking override reaches the request body, symmetric with the two caps.
stub_think = StubTransport(ok(anthropic_end_turn("ok")))
run(task="x", setup=None, log=temp_log("run_think.jsonl"),
    thinking="high", transport=stub_think, sleep=lambda _s: None)
think_body = json.loads(stub_think.calls[0][2])


checks = {
    "one run() call returns the final text and writes the ordered turn phases":
        result1 == "You are in a forest clearing."
        and phases1 == ["session_start", "iteration", "prompt", "response",
                        "tool_call", "tool_result", "iteration", "prompt",
                        "response", "turn_end"]
        and find(lines1, "turn_end")["reason"] == "completed",
    "unset system/model/backend/limits resolve from settings.yaml and task defaults":
        snap1["task"] == "player" and snap1["model"] == "claude-haiku-4-5"
        and snap1["provider"] == "anthropic"
        and snap1["max_iterations"] == 25 and snap1["max_output_tokens"] == 1024,
    "inline tools registered through RunDSL become the registry tools on the prompt":
        prompt2["tools"] == ["read_file", "list_dir"] and prompt2["tool_count"] == 2,
    "the RunDSL exposes only a callable tool, nothing else public":
        public_attrs == ["tool"] and callable(captured["dsl"].tool),
    "explicit model, backend, max_iterations, and max_output_tokens override the snapshot":
        snap4["model"] == "gpt-oss:20b" and snap4["provider"] == "ollama"
        and snap4["max_iterations"] == 7 and snap4["max_output_tokens"] == 64,
    "the seeded task is the first user message on the prompt line":
        prompt1["messages"][0]["role"] == "user"
        and prompt1["messages"][0]["content"][0]["text"] == "Scout the area.",
    "an unknown backend raises, naming the provider":
        error5 is not None and "nope" in error5,
    "setup=None runs a turn with zero tools":
        result6 == "hello" and prompt6["tool_count"] == 0 and prompt6["tools"] == [],
    "a thinking override reaches the request body, symmetric with the caps":
        "thinking" in think_body,
}

print("-- offline invariants (no key, scripted transport) --")
for label, passed in checks.items():
    print(f"  {'PASS' if passed else 'FAIL'} {label}")
assert all(checks.values()), "a run DSL invariant failed"
