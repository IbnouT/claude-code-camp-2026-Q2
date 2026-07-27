"""Reasoning round-trip across the backends, focused on the Ollama gap.

Step 12 introduces a provider-agnostic ReasoningBlock. Anthropic and Gemini
echo it back (signatures round-trip), OpenAI/Ollama drop it on rebuild. Ollama
still has to PARSE its ``message.thinking`` into a ReasoningBlock so the turn can
log and show it. These are pure unit tests on the wire translation, no network.
"""

import unittest

from boukensha.backends import backend_for
from boukensha.context import Context
from boukensha.message import Message, ReasoningBlock, TextBlock, ToolUseBlock


class TestOllamaReasoning(unittest.TestCase):
    def _backend(self):
        return backend_for("ollama", "gpt-oss:20b")

    def test_thinking_parses_to_a_leading_reasoning_block(self):
        parsed = self._backend().parse_response({"message": {
            "thinking": "I should head north to reach the gate.",
            "content": "Heading north.",
        }})
        self.assertIsInstance(parsed.content[0], ReasoningBlock)  # reasoning first
        self.assertIn("head north", parsed.content[0].text)
        self.assertTrue(any(isinstance(b, TextBlock) for b in parsed.content))

    def test_no_thinking_field_yields_no_reasoning_block(self):
        parsed = self._backend().parse_response({"message": {"content": "hi"}})
        self.assertFalse(any(isinstance(b, ReasoningBlock) for b in parsed.content))

    def test_thinking_accompanying_a_tool_call_still_parses(self):
        parsed = self._backend().parse_response({"message": {
            "thinking": "The bakery is east.",
            "tool_calls": [{"function": {"name": "move",
                                         "arguments": {"direction": "east"}}}],
        }})
        self.assertIsInstance(parsed.content[0], ReasoningBlock)
        self.assertTrue(any(isinstance(b, ToolUseBlock) for b in parsed.content))
        self.assertEqual("tool_use", parsed.stop_reason)

    def test_rebuild_drops_reasoning(self):
        # Ollama needs no echo; the reasoning must not reach the wire request.
        be = self._backend()
        ctx = Context("system")
        ctx.add(Message.assistant([ReasoningBlock("private chain of thought"),
                                   TextBlock("done")]))
        blob = str(be._messages(ctx))
        self.assertNotIn("private chain of thought", blob)
        self.assertIn("done", blob)


class TestAnthropicEchoesThinking(unittest.TestCase):
    """Anthropic requires thinking blocks passed back unmodified.

    Per the extended-thinking docs, when a turn continues after a tool call the
    assistant's thinking blocks must be returned exactly as received, signature
    included, or the request is rejected. Rebuilding the assistant turn without
    them is the documented 400, so the echo direction is asserted here.
    https://platform.claude.com/docs/en/build-with-claude/thinking
    """

    def _body_for(self, *blocks):
        backend = backend_for("anthropic", "claude-haiku-4-5")
        context = Context("sys")
        context.add(Message.user("go north"))
        context.add(Message.assistant(blocks))
        return backend.build_request(context)

    def test_thinking_block_is_echoed_with_its_signature(self):
        body = self._body_for(
            ReasoningBlock("Let me consider the exits.", signature="sig-abc"),
            ToolUseBlock("toolu_1", "move", {"direction": "north"}),
        )
        assistant = [m for m in body["messages"] if m["role"] == "assistant"][0]
        thinking = [b for b in assistant["content"] if b.get("type") == "thinking"]
        self.assertEqual(1, len(thinking), "thinking block was not echoed back")
        self.assertEqual("Let me consider the exits.", thinking[0]["thinking"])
        self.assertEqual("sig-abc", thinking[0]["signature"])

    def test_redacted_thinking_is_echoed_as_its_native_type(self):
        # A redacted block carries an opaque payload in place of readable text;
        # it must go back as redacted_thinking with the payload intact.
        body = self._body_for(
            ReasoningBlock("", signature="opaque-data", redacted=True),
            TextBlock("Heading north."),
        )
        assistant = [m for m in body["messages"] if m["role"] == "assistant"][0]
        redacted = [b for b in assistant["content"]
                    if b.get("type") == "redacted_thinking"]
        self.assertEqual(1, len(redacted))
        self.assertEqual("opaque-data", redacted[0]["data"])

    def test_thinking_stays_ahead_of_the_tool_call(self):
        # Order matters on the wire: thinking precedes the tool_use it explains.
        body = self._body_for(
            ReasoningBlock("Think first.", signature="s"),
            ToolUseBlock("toolu_1", "move", {"direction": "north"}),
        )
        assistant = [m for m in body["messages"] if m["role"] == "assistant"][0]
        kinds = [b.get("type") for b in assistant["content"]]
        self.assertLess(kinds.index("thinking"), kinds.index("tool_use"))


class TestGeminiEchoesThoughtSignature(unittest.TestCase):
    """Gemini requires each thought part resent with its thoughtSignature.

    In stateless generateContent the signature is how the model re-associates
    its own prior reasoning, so it round-trips on both the thought part and the
    function call.
    https://ai.google.dev/gemini-api/docs/thinking
    """

    def _parts_for(self, *blocks):
        backend = backend_for("gemini", "gemini-2.5-flash")
        context = Context("sys")
        context.add(Message.user("go north"))
        context.add(Message.assistant(blocks))
        body = backend.build_request(context)
        model_turn = [c for c in body["contents"] if c["role"] == "model"][0]
        return model_turn["parts"]

    def test_thought_part_is_echoed_with_its_signature(self):
        parts = self._parts_for(
            ReasoningBlock("Consider the exits.", signature="thought-sig"))
        thoughts = [p for p in parts if p.get("thought")]
        self.assertEqual(1, len(thoughts), "thought part was not echoed back")
        self.assertEqual("Consider the exits.", thoughts[0]["text"])
        self.assertEqual("thought-sig", thoughts[0]["thoughtSignature"])

    def test_signature_rides_on_the_function_call_too(self):
        parts = self._parts_for(
            ToolUseBlock("move", "move", {"direction": "north"},
                         signature="call-sig"))
        calls = [p for p in parts if "functionCall" in p]
        self.assertEqual(1, len(calls))
        self.assertEqual("call-sig", calls[0]["thoughtSignature"])


if __name__ == "__main__":
    unittest.main()
