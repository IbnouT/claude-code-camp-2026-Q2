"""Step 08: the interactive REPL loop.

The headline is a real session. `repl` runs the interactive loop against the
configured provider: it prints the banner, reads typed lines, runs each as a live
turn (the model calls the MUD tools, and a live activity feed shows it acting),
handles the slash commands, and exits. The typed input is scripted so the run is
reproducible, but the loop and the model are live. Gated behind BOUKENSHA_LIVE=1;
it logs to the real .boukensha/sessions/.

The offline block backs it. Scripted sessions drive the loop over a stub
transport and injected streams, so the loop, the command table, the live feed and
its /quiet toggle, cost and token accounting, interrupt and error isolation, and
the history commands are checked with no key, network, or waiting.
"""

import io
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_BOUKENSHA = Path(__file__).resolve().parents[4] / ".boukensha"
os.environ["BOUKENSHA_DIR"] = str(REPO_BOUKENSHA)

from boukensha import Config, Player, backend_for, repl  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="boukensha-step08-"))


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def phases(lines, phase):
    return [line for line in lines if line["phase"] == phase]


class EchoInput:
    """Echoes each line to an output stream, so a scripted transcript reads like
    a live terminal (an injected stream does not echo as a real tty would)."""

    def __init__(self, script, echo):
        self._lines = io.StringIO(script)
        self._echo = echo

    def readline(self):
        line = self._lines.readline()
        if line:
            self._echo.write(line if line.endswith("\n") else line + "\n")
        return line


# =========================================================================
# The real session: a small MUD world and the interactive loop, live.
# =========================================================================

WORLD = {
    "clearing": ("A sunlit forest clearing. A path leads north and a stream runs east.",
                 {"north": "grove", "east": "brook"}),
    "grove": ("A mossy grove ringed with standing stones. North goes on, south returns.",
              {"north": "cave", "south": "clearing"}),
    "brook": ("A shallow brook. The only way is back west.", {"west": "clearing"}),
    "cave": ("A dark cave mouth. The way south returns to the grove.", {"south": "grove"}),
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

    print("=== boukensha · step 08: the REPL loop (real session) ===")
    print()
    print(f"Config:            {config}")
    print(f"Provider / model:  {provider} / {model}")
    print()

    if os.environ.get("BOUKENSHA_LIVE") != "1":
        print("Real session gated: set BOUKENSHA_LIVE=1 (with the provider key in")
        print(".boukensha/.env) to run the loop live. The offline block runs below.")
        print()
        return
    if backend.api_key_env and not os.environ.get(backend.api_key_env):
        print(f"Real session skipped: BOUKENSHA_LIVE=1 is set but {backend.api_key_env} is not.")
        print("Add it to .boukensha/.env. The offline block runs below.")
        print()
        return

    state = {"room": "clearing"}
    script = "look around\nmove north\n/tools\n/cost\n/exit\n"
    print("A real interactive session (typed lines scripted; banner, replies,")
    print("tool calls, and the live feed are real):")
    print()
    repl(setup=mud_setup(state),
         input=EchoInput(script, sys.stdout), output=sys.stdout)
    print()


run_live()


# =========================================================================
# Offline invariants. Scripted sessions over a stub transport and streams.
# =========================================================================

class StubTransport:
    """Replays scripted steps; a step is a reply tuple or an exception to raise.
    The last step repeats. Records every call."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, BaseException):
            raise step
        return step


def end_turn(text, in_tok=1200, out_tok=80):
    return (200, json.dumps({
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }), {})


def tool_use(name, args, cid="t1"):
    return (200, json.dumps({
        "stop_reason": "tool_use",
        "content": [{"type": "text", "text": "acting"},
                    {"type": "tool_use", "id": cid, "name": name, "input": args}],
        "usage": {"input_tokens": 500, "output_tokens": 20},
    }), {})


def ollama_end_turn(text):
    return (200, json.dumps({
        "message": {"role": "assistant", "content": text},
        "prompt_eval_count": 20, "eval_count": 6,
    }), {})


def unauthorized():
    return (401, json.dumps({"type": "error",
                             "error": {"type": "authentication_error"}}), {})


def session(script, transport, name, setup=None):
    out = io.StringIO()
    log = str(TMP / f"{name}.jsonl")
    repl(input=io.StringIO(script), output=out, log=log,
         transport=transport, sleep=lambda _s: None, setup=setup)
    return out.getvalue(), read_lines(log)


def move_setup(dsl):
    @dsl.tool("move", description="Move the player.",
              parameters={"direction": {"type": "string"}})
    def move(direction):
        return f"You move {direction}."


# A: banner, two plain turns, history accumulation, per-turn counters.
out_a, log_a = session("look around\ngo north\n/exit\n",
                       StubTransport(end_turn("A dim corridor."),
                                     end_turn("You head north.")), "a")
prompts_a = phases(log_a, "prompt")

# B: /help is generated from the table (lists /quit, the old drift bug).
out_b, _ = session("/help\n/exit\n", StubTransport(end_turn("x")), "b")

# C: unknown /word is rejected (no turn); // sends a literal /line to the agent.
t_c = StubTransport(end_turn("ok"))
out_c, log_c = session("/nope\n//say hi\n/exit\n", t_c, "c")
prompt_c = phases(log_c, "prompt")

# D: the live feed shows tool calls; /quiet suppresses them.
out_d_loud, _ = session("explore\n/exit\n",
                        StubTransport(tool_use("move", {"direction": "north"}),
                                      end_turn("done")), "d1", setup=move_setup)
out_d_quiet, _ = session("/quiet\nexplore\n/exit\n",
                         StubTransport(tool_use("move", {"direction": "north"}),
                                       end_turn("done")), "d2", setup=move_setup)

# E: /cost and /tokens accumulate across turns.
out_e, _ = session("a\nb\n/tokens\n/cost\n/exit\n",
                   StubTransport(end_turn("one"), end_turn("two")), "e")

# F: Ctrl-C aborts one turn; the loop continues, history stays well-formed.
t_f = StubTransport(KeyboardInterrupt(), end_turn("recovered"))
out_f, _ = session("cause\nrecover\n/exit\n", t_f, "f")
recover_body = t_f.calls[-1][2]

# G: an unexpected error is isolated; the session continues.
out_g, _ = session("boom\nok\n/exit\n",
                   StubTransport(RuntimeError("kaboom"), end_turn("fine")), "g")

# H: /undo drops the last turn; /retry drops and reruns it.
out_h_undo, _ = session("hello\n/undo\n/exit\n",
                        StubTransport(end_turn("hi")), "h1")
t_h = StubTransport(end_turn("first"), end_turn("second"))
out_h_retry, _ = session("hello\n/retry\n/exit\n", t_h, "h2")

# I: /model switches the backend mid-session; history survives.
t_i = StubTransport(ollama_end_turn("from ollama"))
out_i, log_i = session("/model ollama gpt-oss:20b\ntalk\n/exit\n", t_i, "i")
switch_url = t_i.calls[-1][0] if t_i.calls else ""

# J: /clear wipes history and resets the counter.
out_j, log_j = session("one\n/clear\ntwo\n/exit\n",
                       StubTransport(end_turn("r1"), end_turn("r2")), "j")
turns_j = phases(log_j, "turn")
prompt_after_clear = phases(log_j, "prompt")[1]

# K: /exit and /quit end the loop; later lines are not processed.
t_k = StubTransport(end_turn("unused"))
out_k, log_k = session("/quit\nnever\n", t_k, "k")

# L: a 401 turn surfaces the error and the loop continues.
out_l, _ = session("cause 401\nrecover\n/exit\n",
                   StubTransport(unauthorized(), end_turn("You recovered.")), "l")

# M: a backslash-continued line is one turn carrying the joined multi-line text.
out_m, log_m = session("tell me \\\nabout dragons\n/exit\n",
                       StubTransport(end_turn("A tale.")), "m")
prompt_m = phases(log_m, "prompt")[0]
text_m = "".join(b.get("text", "") for b in prompt_m["messages"][0]["content"])
turns_m = phases(log_m, "turn")


checks = {
    "the banner prints first with version, provider, model, config dir, and tools line":
        "BOUKENSHA MUD Assistant  (v0.8.0)" in out_a
        and "anthropic (claude-haiku-4-5)" in out_a
        and "tools:" in out_a and str(REPO_BOUKENSHA) in out_a
        and out_a.index("v0.8.0") < out_a.index("A dim corridor."),
    "plain lines run turns: replies written, history carries prior turns, one iteration per turn":
        "A dim corridor." in out_a
        and "".join(b.get("text", "") for b in prompts_a[1]["messages"][0]["content"]) == "look around"
        and [t["n"] for t in phases(log_a, "turn")] == [1, 2]
        and [it["n"] for it in phases(log_a, "iteration")] == [1, 1],
    "/help is generated from the command table (lists /quit, the aliased exit)":
        "Commands:" in out_b and "/quit" in out_b and "/tools" in out_b,
    "an unknown /word is rejected with no turn; // sends a literal /line to the agent":
        "unknown command: /nope" in out_c and len(t_c.calls) == 1
        and "".join(b.get("text", "") for b in prompt_c[0]["messages"][0]["content"]) == "/say hi",
    "the live feed shows tool calls, and /quiet suppresses it":
        "-> move" in out_d_loud and "-> move" not in out_d_quiet,
    "/cost and /tokens accumulate across turns":
        "2400 in / 160 out" in out_e and "0.0032" in out_e,
    "Ctrl-C aborts one turn, the loop continues, and history stays well-formed":
        "[aborted]" in out_f and "recovered" in out_f
        and "[turn aborted by user]" in recover_body,
    "an unexpected error is isolated and the session continues":
        "[error] unexpected: RuntimeError" in out_g and "fine" in out_g,
    "/undo drops the last turn; /retry drops and reruns it":
        "(dropped: hello)" in out_h_undo
        and "(retrying: hello)" in out_h_retry and len(t_h.calls) == 2,
    "/model switches the backend mid-session (request goes to the new backend)":
        "localhost:11434/api/chat" in switch_url,
    "/clear wipes history and resets the counter to 1":
        turns_j[1]["n"] == 1 and len(prompt_after_clear["messages"]) == 1,
    "/exit and /quit end the loop, later lines unprocessed":
        "Goodbye." in out_k and len(t_k.calls) == 0
        and len(phases(log_k, "turn")) == 0,
    "a 401 turn surfaces the error and the loop continues to the next turn":
        "authentication failed (401)" in out_l and "You recovered." in out_l,
    "a backslash-continued line is one turn carrying the joined multi-line text":
        text_m == "tell me \nabout dragons" and len(turns_m) == 1,
}

print("-- offline invariants (no key, scripted transport) --")
for label, passed in checks.items():
    print(f"  {'PASS' if passed else 'FAIL'} {label}")
assert all(checks.values()), "a REPL invariant failed"
