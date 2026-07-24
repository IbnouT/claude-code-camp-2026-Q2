"""Step 04: the API client.

The headline is a real round trip. The client posts the request the builder
assembled to the configured provider and prints the raw parsed reply. Running it
is the demonstration, and it needs the provider's API key (see .boukensha/.env).
Local Ollama needs none. Without a key the real call is skipped with a notice and
the offline block below still runs.

That offline block is where the client's real substance lives: the retry and
error behavior, which a single live call cannot show on demand. Scripted
transports stand in for the network and a recording function stands in for
sleep, so a healed retry, an exhausted retry, a hard failure, a bad body, and
the per-provider auth wiring are all checked without keys, sockets, or waiting.

Retry policy sources, fetched 2026-07-23:
- https://platform.claude.com/docs/en/api/errors documents 409, 429, 500, 504,
  and 529 (overloaded_error) as retryable, states the official SDKs retry
  transient failures with exponential backoff, and states they honor the
  retry-after header. 529 and Retry-After handling derive from this page.
- 408, 502, and 503 complete the set: standard transient HTTP statuses (request
  timeout, bad gateway, service unavailable) that every provider's edge emits.
"""

import io
import json
import os
from contextlib import redirect_stdout

from boukensha import (
    ApiError,
    Client,
    Config,
    Context,
    Message,
    Player,
    PromptBuilder,
    Registry,
    Tool,
    backend_for,
)

# =========================================================================
# The real round trip: build the request the configured provider expects,
# post it, and print the raw parsed reply.
# =========================================================================


def _indent(text, pad="    "):
    return "\n".join(pad + line for line in text.splitlines())


def run_live():
    config = Config()
    settings = config.tasks("player")
    provider = Player.provider(settings)
    model = Player.model(settings)
    backend = backend_for(provider, model)

    ctx = Context(system="You are a MUD player agent exploring a text world.")
    ctx.add(Message.user("Look around and tell me what you see."))
    registry = Registry()
    registry.register(Tool(
        "look", "Describe the current room and its exits.", {},
        lambda: "A forest clearing. Exits: north, east.",
    ))
    builder = PromptBuilder(ctx, backend, tuple(registry.tools.values()))
    client = Client(builder)

    print("=== boukensha · step 04: api client (real round trip) ===")
    print()
    print(f"Config:            {config}")
    print(f"Provider / model:  {provider} / {model}")
    print()

    # The built request: the endpoint, the auth headers (secrets redacted), and
    # the JSON body the PromptBuilder assembled. This is what the client posts.
    print(f"Built request:     POST {builder.url()}")
    print("  headers:")
    for key, value in builder.headers().items():
        secret = key.lower() in ("x-api-key", "authorization", "x-goog-api-key")
        print(f"    {key}: {'***redacted***' if secret else value}")
    print("  body:")
    print(_indent(json.dumps(builder.build_request(), indent=2)))
    print()

    if os.environ.get("BOUKENSHA_LIVE") != "1":
        print("Real call gated: set BOUKENSHA_LIVE=1 (with the provider key in")
        print(".boukensha/.env) to post it for real. The offline block runs below.")
        print()
        return
    if backend.api_key_env and not os.environ.get(backend.api_key_env):
        print(f"Real call skipped: BOUKENSHA_LIVE=1 is set but {backend.api_key_env} is not.")
        print("Add it to .boukensha/.env. The offline block runs below.")
        print()
        return

    print("Posting it. The client returns the provider's raw parsed reply:")
    print()
    print(_indent(json.dumps(client.call(), indent=2)))
    print()


run_live()


# =========================================================================
# Offline: retry and error behavior over scripted transports. No key, no
# network, no waiting. Each client records the calls it made and the sleeps
# it asked for, so the backoff schedule and the attempt count are visible.
# =========================================================================

MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-5.4",
    "gemini": "gemini-3.1-pro-preview",
    "ollama": "gpt-oss:20b",
    "ollama_cloud": "gpt-oss:120b",
}

OK = (200, '{"id": "msg_1", "content": [{"type": "text", "text": "ok"}]}', {})


class StubTransport:
    """Replays scripted steps in order; a step is a (status, body, headers)
    tuple or an exception to raise. The last step repeats if the script runs
    out. Records every call."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step


def make_client(*script, provider="anthropic"):
    """A client over a scripted transport and a recording sleep."""
    ctx = Context(system="You are a MUD player agent.")
    ctx.add(Message.user("Look around."))
    move = Tool("move", "Move in a direction.",
                {"direction": {"type": "string"}}, lambda direction: "ok")
    builder = PromptBuilder(ctx, backend_for(provider, MODELS[provider]), (move,))
    transport = StubTransport(*script)
    sleeps = []
    return Client(builder, transport=transport, sleep=sleeps.append), transport, sleeps


def failure(client):
    """The ApiError a call raises, or None if it unexpectedly succeeds."""
    try:
        client.call()
        return None
    except ApiError as exc:
        return exc


with redirect_stdout(io.StringIO()):
    # A transient status heals on the retry.
    c_heal, t_heal, s_heal = make_client((429, "slow down", {}), OK)
    r_heal = c_heal.call()

    # A persistent transient status walks the full backoff, then stops.
    c_exh, t_exh, s_exh = make_client((429, '{"error": "rate limited"}', {}))
    e_exh = failure(c_exh)

    # A non-retryable status fails at once, no sleep.
    c_hard, t_hard, s_hard = make_client((401, '{"error": "bad key"}', {}))
    e_hard = failure(c_hard)

    # A numeric Retry-After replaces the backoff wait, capped at 60 s.
    c_ra, _t_ra, s_ra = make_client((429, "wait", {"Retry-After": "999"}), OK)
    c_ra.call()

    # A 2xx body that is not JSON fails with the evidence attached.
    c_bad, _t_bad, _s_bad = make_client((200, "<html>gateway error</html>", {}))
    e_bad = failure(c_bad)

    # A transient exception (a connection cut mid-response) is retried.
    c_cut, t_cut, s_cut = make_client(EOFError("eof mid-response"), OK)
    r_cut = c_cut.call()

    # One provider-blind client, five endpoints, each with its auth form.
    wire = {}
    for name in MODELS:
        c, t, _ = make_client(OK, provider=name)
        c.call()
        wire[name] = t.calls[0]


checks = {
    "a 429 then a 200 returns the parsed reply on the second attempt, one 0.5 s sleep":
        r_heal == json.loads(OK[1]) and len(t_heal.calls) == 2 and s_heal == [0.5],
    "a persistent 429 sleeps 0.5, 1.0, 2.0 over 4 attempts, then raises naming the status":
        s_exh == [0.5, 1.0, 2.0] and len(t_exh.calls) == 4
        and "4 attempts" in str(e_exh) and "429" in str(e_exh),
    "a 401 raises on the first attempt with no sleep, status and body named":
        len(t_hard.calls) == 1 and s_hard == []
        and "401" in str(e_hard) and "bad key" in str(e_hard),
    "a numeric Retry-After replaces the wait and is capped at 60 s":
        s_ra == [60.0],
    "a 2xx body that is not JSON raises ApiError with a body preview":
        "200" in str(e_bad) and "<html>gateway error</html>" in str(e_bad),
    "a connection cut mid-response is transient: retried, then returns":
        r_cut == json.loads(OK[1]) and len(t_cut.calls) == 2 and s_cut == [0.5],
    "five backends each POST to their endpoint with their auth form":
        "api.anthropic.com" in wire["anthropic"][0]
        and "x-api-key" in wire["anthropic"][1]
        and "api.openai.com" in wire["openai"][0]
        and wire["openai"][1]["Authorization"].startswith("Bearer")
        and "generativelanguage.googleapis.com" in wire["gemini"][0]
        and "x-goog-api-key" in wire["gemini"][1]
        and "localhost:11434" in wire["ollama"][0]
        and "Authorization" not in wire["ollama"][1]
        and "ollama.com" in wire["ollama_cloud"][0]
        and wire["ollama_cloud"][1]["Authorization"].startswith("Bearer"),
}

print("-- offline invariants (no key, scripted transport) --")
for label, passed in checks.items():
    print(f"  {'PASS' if passed else 'FAIL'} {label}")
assert all(checks.values()), "an API-client invariant failed"
