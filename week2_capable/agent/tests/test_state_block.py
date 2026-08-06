"""The knowledge state block: volatile injection and its wiring."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from boukensha import run_dsl
from boukensha.agent import Agent
from boukensha.registry import Registry
from boukensha.tasks import Player

from .helper import StubTransport, end_turn, ok

TMP = Path(tempfile.mkdtemp(prefix="boukensha-state-block-"))


class CapturingTransport(StubTransport):
    """Retains every request body the client sent."""

    def __init__(self, *script):
        super().__init__(*script)
        self.bodies = []

    def __call__(self, url, headers, body):
        self.bodies.append(json.loads(body))
        return super().__call__(url, headers, body)


def build_agent(transport, name, state_block_source):
    assembled = run_dsl._assemble(
        system=None, model=None, backend=None, api_key=None,
        ollama_host="http://localhost:11434",
        log=str(TMP / f"{name}.jsonl"),
        max_output_tokens=None, context_window=None, setup=None,
        transport=transport, sleep=lambda _s: None)
    agent = Agent(
        assembled.context, assembled.registry, assembled.builder,
        assembled.client, task=Player,
        task_settings=assembled.task_settings,
        logger=assembled.logger,
        state_block_source=state_block_source,
    )
    return agent, assembled


class TestVolatileStateBlock(unittest.TestCase):
    def test_block_rides_the_request_and_never_stays_in_history(self):
        transport = CapturingTransport(ok(end_turn("done")))
        agent, assembled = build_agent(
            transport, "rides", lambda: "[here] The Temple"
        )
        assembled.context.add(
            run_dsl.Message.user("Find the minotaur and kill it.")
        )
        agent.run()

        sent = transport.bodies[0]["messages"]
        self.assertEqual("user", sent[-1]["role"])
        self.assertIn("[state]", sent[-1]["content"][0]["text"])
        self.assertIn("[here] The Temple", sent[-1]["content"][0]["text"])
        retained = [
            block.text
            for message in assembled.context.messages
            for block in message.content
            if hasattr(block, "text")
        ]
        self.assertFalse(
            any("[state]" in text for text in retained),
            "the volatile block must never persist in history",
        )

    def test_failing_source_never_breaks_the_call(self):
        def broken():
            raise RuntimeError("store unavailable")

        transport = CapturingTransport(ok(end_turn("done")))
        agent, assembled = build_agent(transport, "broken", broken)
        assembled.context.add(
            run_dsl.Message.user("Find the minotaur and kill it.")
        )
        result = agent.run()

        self.assertTrue(result)
        sent = transport.bodies[0]["messages"]
        self.assertNotIn("[state]", json.dumps(sent))
        log_text = Path(assembled.logger.path).read_text()
        self.assertIn("state_block_failed", log_text)


class TestStateBlockWiring(unittest.TestCase):
    class _Config:
        def __init__(self, enabled):
            self._enabled = enabled

        def capability(self, name):
            return self._enabled and name == "knowledge"

    def test_source_absent_when_flag_off_or_tool_missing(self):
        registry = Registry()
        off = run_dsl._state_block_source(self._Config(False), registry)
        self.assertIsNone(off)
        on_no_tool = run_dsl._state_block_source(self._Config(True), registry)
        self.assertIsNone(on_no_tool)

    def test_source_dispatches_the_prefixed_tool(self):
        registry = Registry()

        @registry.tool("mud__recall_state", "state")
        def recall_state():
            return "[here] rendered"

        source = run_dsl._state_block_source(self._Config(True), registry)
        self.assertIsNotNone(source)
        self.assertEqual("[here] rendered", source())


class TestStateFields(unittest.TestCase):
    def test_valid_line_reaches_the_sink_and_the_log(self):
        from boukensha.state_fields import parse_state_fields

        fields = parse_state_fields(
            'Moving on.\nSTATE {"perceive": "dark", "threat": null, '
            '"learned": "the alley is unlit"}'
        )
        self.assertEqual(
            {"perceive": "dark", "threat": None,
             "learned": "the alley is unlit"},
            fields,
        )

        captured = []
        transport = CapturingTransport(ok(end_turn(
            'Done.\nSTATE {"perceive": "clear", "threat": null, '
            '"learned": null}'
        )))
        agent, assembled = build_agent(transport, "fields", None)
        agent._state_fields_sink = captured.append
        assembled.context.add(
            run_dsl.Message.user("Find the minotaur and kill it.")
        )
        agent.run()
        self.assertEqual(1, len(captured))
        self.assertEqual("clear", captured[0]["perceive"])
        log_text = Path(assembled.logger.path).read_text()
        self.assertIn("state_fields", log_text)

    def test_missing_or_malformed_line_is_counted_not_raised(self):
        from boukensha.state_fields import parse_state_fields

        self.assertIsNone(parse_state_fields("no line here"))
        self.assertIsNone(parse_state_fields('STATE {"perceive": "purple"}'))

        captured = []
        transport = CapturingTransport(ok(end_turn("Done, no state line.")))
        agent, assembled = build_agent(transport, "fields-missing", None)
        agent._state_fields_sink = captured.append
        assembled.context.add(
            run_dsl.Message.user("Find the minotaur and kill it.")
        )
        agent.run()
        self.assertEqual([], captured)
        log_text = Path(assembled.logger.path).read_text()
        self.assertIn("state_fields_missing", log_text)


if __name__ == "__main__":
    unittest.main()
