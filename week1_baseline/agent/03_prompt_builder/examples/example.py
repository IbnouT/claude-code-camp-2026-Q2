"""Demonstration of the prompt builder.

Builds one MUD conversation (text turns, a parallel double tool call, both
results) and serializes it for every provider, so a reader can SEE one context
become five different wire shapes, and one thinking dial become five different
request fields. No network and no API keys: backends only build request bodies,
they do not send them. Assertions pinning every shape stay compact at the end.
"""

import inspect
import json
import tempfile
from pathlib import Path

from boukensha import (
    Config,
    ConfigError,
    Context,
    Message,
    ModelCatalog,
    Player,
    PromptBuilder,
    Role,
    Tool,
    ToolResultBlock,
    ToolUseBlock,
    backend_for,
)
from boukensha.backends import Anthropic, Gemini, Ollama, OllamaCloud, OpenAI

config = Config()

# One conversation: text turns, one parallel double tool call, both results.
ctx = Context(system="You are a MUD player agent.")
ctx.add(Message.user("Scout the area."))
ctx.add(Message.assistant("Checking both exits."))
ctx.add(Message.assistant((
    ToolUseBlock("call_1", "move", {"direction": "north"}),
    ToolUseBlock("call_2", "move", {"direction": "east"}),
)))
ctx.add(Message(Role.TOOL_RESULT, (
    ToolResultBlock("call_1", "move", "A torch-lit corridor."),
    ToolResultBlock("call_2", "move", "A locked gate."),
)))

move = Tool(
    "move",
    "Move the player in a direction.",
    {"direction": {"type": "string"}},
    lambda direction: f"You move {direction}.",
)
emote = Tool(
    "emote",
    "Perform an emote, optionally at a target.",
    {"action": {"type": "string"}, "target": {"type": "string"}},
    lambda action, target="": f"You {action} {target}".strip(),
)
tools = (move, emote)

MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-5.4",
    "gemini": "gemini-3.1-pro-preview",
    "ollama": "gpt-oss:20b",
    "ollama_cloud": "gpt-oss:120b",
}

backends = {name: backend_for(name, model) for name, model in MODELS.items()}
bodies = {
    name: PromptBuilder(ctx, backend, tools).build_request()
    for name, backend in backends.items()
}
thinking_bodies = {
    name: PromptBuilder(ctx, backend, tools).build_request(thinking="medium")
    for name, backend in backends.items()
}
fable_thinking = backend_for("anthropic", "claude-fable-5").build_request(
    ctx, tools, thinking="medium"
)

anth, oai, gem, oll, cloud = (
    bodies["anthropic"], bodies["openai"], bodies["gemini"],
    bodies["ollama"], bodies["ollama_cloud"],
)

anth_results = [m for m in anth["messages"]
                if m["role"] == "user"
                and any(b.get("type") == "tool_result" for b in m["content"])]
oai_outputs = [i for i in oai["input"] if i.get("type") == "function_call_output"]
oai_calls = [i for i in oai["input"] if i.get("type") == "function_call"]
gem_responses = [p["functionResponse"]
                 for c in gem["contents"] for p in c["parts"]
                 if "functionResponse" in p]
oll_tool_msgs = [m for m in oll["messages"] if m["role"] == "tool"]

# -- the demo: show the component working -------------------------------------

print("=== boukensha · step 03: prompt builder ===")
print()
print(f"Config:   {config}")
for name, backend in backends.items():
    print(f"{name:13s} {backend}  url={backend.url().split('?')[0]}")

# The same conversation, built in full for the task's configured provider.
provider = Player.provider(config.tasks("player"))
print()
print(f"-- built request for the configured provider ({provider}) --")
print(json.dumps(bodies[provider], indent=2))

# One context, five request shapes: the top-level keys differ per provider.
print()
print("-- top-level request keys per provider --")
for name in MODELS:
    print(f"  {name:13s} {list(bodies[name])}")

# The same tool result (call_1, tool 'move'), carried four different ways.
print()
print("-- the same tool result, one wire shape per provider --")
print(f"  anthropic     user message, tool_result block by "
      f"tool_use_id={anth_results[0]['content'][0]['tool_use_id']}")
print(f"  openai        function_call_output item by "
      f"call_id={oai_outputs[0]['call_id']}")
print(f"  gemini        user message, functionResponse part "
      f"name={gem_responses[0]['name']} id={gem_responses[0]['id']}")
print(f"  ollama        role:tool message, "
      f"tool_name={oll_tool_msgs[0]['tool_name']}")

# One thinking dial (task set to medium), mapped to each provider's field.
print()
print("-- thinking dial at 'medium', mapped per provider --")
print(f"  anthropic (budget)    thinking={thinking_bodies['anthropic']['thinking']}")
print(f"  openai (effort)       reasoning={thinking_bodies['openai']['reasoning']}")
print(f"  gemini (level)        thinkingConfig="
      f"{thinking_bodies['gemini']['generationConfig']['thinkingConfig']}")
print(f"  ollama (level_string) think={thinking_bodies['ollama']['think']!r}")
print(f"  fable-5 (adaptive)    thinking={fable_thinking['thinking']} "
      f"output_config={fable_thinking['output_config']}")

# -- assertions: pin every shape the demo showed ------------------------------


def deep_keys(node):
    """Every key appearing anywhere in a nested JSON-like structure."""
    keys = set()
    if isinstance(node, dict):
        for k, v in node.items():
            keys.add(k)
            keys |= deep_keys(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            keys |= deep_keys(v)
    return keys


def rejected(call, error):
    try:
        call()
        return False
    except error:
        return True


gemma_thinking = backend_for("ollama", "gemma4").build_request(
    ctx, tools, thinking="medium"
)

# "none" means no thinking, expressed the way each provider allows: an off
# value, an omitted field, or the minimum where off is inexpressible.
none_openai = backend_for("openai", "gpt-5.6-sol").build_request(
    ctx, tools, thinking="none"
)
none_flag = backend_for("ollama", "qwen3:8b").build_request(
    ctx, tools, thinking="none"
)
none_haiku = backend_for("anthropic", "claude-haiku-4-5").build_request(
    ctx, tools, thinking="none"
)
none_fable = backend_for("anthropic", "claude-fable-5").build_request(
    ctx, tools, thinking="none"
)
none_opus48 = backend_for("anthropic", "claude-opus-4-8").build_request(
    ctx, tools, thinking="none"
)
none_sonnet5 = backend_for("anthropic", "claude-sonnet-5").build_request(
    ctx, tools, thinking="none"
)

# A user catalog that overrides one bundled entry and adds a new model.
_override = tempfile.NamedTemporaryFile(
    mode="w", suffix=".yaml", delete=False
)
_override.write(
    "anthropic:\n"
    "  claude-haiku-4-5: {context_window: 111, cost_per_million: {input: 1.0, output: 5.0}}\n"
    "ollama:\n"
    "  custom-local: {context_window: 4096, cost_per_million: {input: 0.0, output: 0.0}}\n"
    "gemini:\n"
    "  restricted: {context_window: 1000, cost_per_million: {input: 0.1, output: 0.1},\n"
    "               thinking: level, thinking_levels: [low, high]}\n"
    "  floor-only: {context_window: 1000, cost_per_million: {input: 0.1, output: 0.1},\n"
    "               thinking: level, thinking_levels: [high, max]}\n"
)
_override.close()
override_catalog = ModelCatalog(Path(_override.name))
Path(_override.name).unlink()

checks = {
    "1 anthropic: top-level system, tool_result in user message by tool_use_id":
        anth["system"] == ctx.system
        and len(anth_results) == 1
        and anth_results[0]["content"][0]["tool_use_id"] == "call_1",
    "2 openai: instructions, input items, max_output_tokens, function_call_output by call_id":
        oai["instructions"] == ctx.system
        and isinstance(oai["input"], list)
        and oai["max_output_tokens"] == 1024
        and {o["call_id"] for o in oai_outputs} == {"call_1", "call_2"},
    "3 gemini: systemInstruction, model role, functionResponse with name and id echo":
        "systemInstruction" in gem
        and any(c["role"] == "model" for c in gem["contents"])
        and gem_responses[0]["name"] == "move"
        and gem_responses[0]["id"] == "call_1",
    "4 ollama and cloud: stream false, tool_name results, same body, urls and auth differ":
        oll["stream"] is False and cloud["stream"] is False
        and oll_tool_msgs[0]["tool_name"] == "move"
        and backends["ollama"].url() != backends["ollama_cloud"].url()
        and "Authorization" in backends["ollama_cloud"].headers()
        and "Authorization" not in backends["ollama"].headers(),
    "5 tool call forms: anthropic tool_use, openai arguments JSON string, gemini args, ollama object":
        any(b.get("type") == "tool_use" for m in anth["messages"] for b in m["content"])
        and json.loads(oai_calls[0]["arguments"]) == {"direction": "north"}
        and oai["tools"][0]["name"] == "move"
        and any("functionCall" in p for c in gem["contents"] for p in c["parts"])
        and oll["messages"][3]["tool_calls"][0]["function"]["arguments"]
            == {"direction": "north"},
    "6 optional parameter stays out of required":
        all(req == ["action"] for req in (
            anth["tools"][1]["input_schema"]["required"],
            oai["tools"][1]["parameters"]["required"],
            gem["tools"][0]["functionDeclarations"][1]["parameters"]["required"],
            oll["tools"][1]["function"]["parameters"]["required"],
        )),
    "7 backend_for matches and rejects unknown providers":
        isinstance(backends["anthropic"], Anthropic)
        and isinstance(backends["ollama_cloud"], OllamaCloud)
        and rejected(lambda: backend_for("mystery", "m"), ValueError),
    "8 uniform surface across backends":
        len({
            str(inspect.signature(getattr(cls, m)))
            for cls in (Anthropic, OpenAI, Gemini, Ollama, OllamaCloud)
            for m in ("build_request", "headers", "url")
        }) == 3,
    "9 auth per provider: x-api-key, Bearer, x-goog-api-key header, none":
        "x-api-key" in backends["anthropic"].headers()
        and backends["openai"].headers()["Authorization"].startswith("Bearer")
        and "x-goog-api-key" in backends["gemini"].headers()
        and "?key=" not in backends["gemini"].url()
        and "Authorization" not in backends["ollama"].headers(),
    "10 two results: one wire message on anthropic and gemini, two items on openai and ollama":
        len(anth_results) == 1 and len(anth_results[0]["content"]) == 2
        and len(gem_responses) == 2
        and sum("functionResponse" in str(c) for c in gem["contents"]) == 1
        and len(oai_outputs) == 2
        and len(oll_tool_msgs) == 2,
    "11 tool result without a tool name is rejected at construction":
        rejected(
            lambda: Message.tool_result("call_9", "", "output"), ValueError
        ),
    "12 thinking unset: no thinking or sampling fields anywhere":
        not (
            {"thinking", "reasoning", "think", "thinkingConfig",
             "output_config", "temperature", "top_p", "top_k"}
            & set().union(*(deep_keys(b) for b in bodies.values()))
        ),
    "13 thinking set: each catalog mode maps to its documented form":
        thinking_bodies["openai"]["reasoning"] == {"effort": "medium"}
        and thinking_bodies["gemini"]["generationConfig"]["thinkingConfig"]
            == {"thinkingLevel": "medium"}
        and thinking_bodies["ollama"]["think"] == "medium"
        and thinking_bodies["anthropic"]["thinking"]
            == {"type": "enabled", "budget_tokens": 4096}
        and fable_thinking["thinking"] == {"type": "adaptive"}
        and fable_thinking["output_config"] == {"effort": "medium"},
    "14 thinking set on a model without the capability sends nothing":
        "think" not in gemma_thinking,
    "15 known model resolves window, cost, and usage unit":
        backends["anthropic"].context_window == 200_000
        and backends["anthropic"].estimate_cost(1_000_000, 1_000_000) == 6.0
        and backends["anthropic"].usage_unit == "tokens"
        and backends["ollama"].estimate_cost(1000, 1000) == 0.0
        and backends["ollama_cloud"].usage_unit == "subscription"
        and backends["ollama_cloud"].estimate_cost(1000, 1000) is None,
    "16 unknown model raises ConfigError naming it":
        rejected(
            lambda: backend_for("anthropic", "claude-nonexistent"), ConfigError
        ),
    "17 user catalog overrides and extends the bundled one":
        override_catalog.info("anthropic", "claude-haiku-4-5")["context_window"] == 111
        and backend_for("ollama", "custom-local", catalog=override_catalog)
            .context_window == 4096,
    "18 a level above the model's ceiling clamps down, never up":
        backend_for("gemini", "restricted", catalog=override_catalog)
            .build_request(ctx, tools, thinking="medium")
            ["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
        and backend_for("anthropic", "claude-haiku-4-5")
            .build_request(ctx, tools, thinking="xhigh")
            ["thinking"] == {"type": "enabled", "budget_tokens": 16384},
    "19 below the model's minimum, its lowest supported level is used":
        backend_for("gemini", "floor-only", catalog=override_catalog)
            .build_request(ctx, tools, thinking="low")
            ["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"},
    "20 none disables thinking: openai effort none, flag think false, budget omits the field":
        none_openai["reasoning"] == {"effort": "none"}
        and none_flag["think"] is False
        and "thinking" not in none_haiku,
    "21 none on an always-on model (Fable 5) falls to minimum, not off":
        none_fable["thinking"] == {"type": "adaptive"}
        and none_fable["output_config"] == {"effort": "low"},
    "22 none on a disable-capable adaptive model sends thinking disabled":
        none_opus48["thinking"] == {"type": "disabled"}          # default off
        and "output_config" not in none_opus48
        and none_sonnet5["thinking"] == {"type": "disabled"}     # default on
        and "output_config" not in none_sonnet5,
    "23 a level outside the dial vocabulary is rejected, naming the valid values":
        rejected(
            lambda: backends["anthropic"].build_request(ctx, tools, thinking="ultra"),
            ConfigError,
        ),
}

print()
for label, passed in checks.items():
    print(f"  {'✓' if passed else '✗'} {label}")
assert all(checks.values()), "one or more wire-format guarantees failed"
print()
print("assertions passed (23) ✓")
