"""Ceilings a person can see and change, and a turn they can pick up again.

A limit nobody can reach is a dead end. These drive the real command table, so a
handler that stops working fails here rather than in someone's session.
"""

import io
import tempfile
import unittest
from pathlib import Path

from boukensha import run_dsl
from boukensha.repl import Repl

from .helper import StubTransport, end_turn, ok, tool_use

TMP = Path(tempfile.mkdtemp(prefix="boukensha-limits-"))


def build_repl(transport, name, **kwargs):
    assembled = run_dsl._assemble(
        system=None, model=None, backend=None, api_key=None,
        ollama_host="http://localhost:11434", log=str(TMP / f"{name}.jsonl"),
        max_output_tokens=None, context_window=None, setup=None,
        transport=transport, sleep=lambda _s: None)
    out = io.StringIO()
    repl = Repl(context=assembled.context, registry=assembled.registry,
                builder=assembled.builder, client=assembled.client,
                logger=assembled.logger, task_settings=assembled.task_settings,
                max_iterations=assembled.max_iterations,
                max_output_tokens=assembled.max_output_tokens,
                config_dir=assembled.config_dir, provider=assembled.provider,
                model=assembled.model, version="test", api_key=None,
                servers=assembled.servers, output=out, **kwargs)
    return repl, out, assembled


class TestLimitsReports(unittest.TestCase):
    def test_every_ceiling_shows_current_over_limit(self):
        # The numerator alone cannot warn anyone: the figure that ended a turn was
        # 62,357 against 60,000 and only the first half was ever on screen.
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("hi"))), "report",
            max_turn_tokens=60000, max_turn_cost=0.25)
        repl.handle_command("/limits")
        text = out.getvalue()
        for name in ("iterations", "turn_tokens", "turn_cost", "window"):
            self.assertIn(name, text)
        self.assertIn("60000", text)
        self.assertIn("0.25", text)
        assembled.logger.close()

    def test_a_disabled_ceiling_says_disabled_rather_than_zero(self):
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("hi"))), "disabled",
            max_turn_tokens=0, max_turn_cost=0)
        repl.handle_command("/limits")
        self.assertIn("disabled", out.getvalue())
        assembled.logger.close()


class TestLimitsSets(unittest.TestCase):
    def test_setting_a_ceiling_changes_what_the_next_turn_enforces(self):
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("hi"))), "set", max_turn_cost=0.10)
        repl.handle_command("/limits turn_cost 0.50")
        self.assertEqual(0.50, repl.max_turn_cost)
        self.assertIn("next turn", out.getvalue())
        assembled.logger.close()

    def test_zero_disables_and_says_so(self):
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("hi"))), "zero", max_turn_tokens=60000)
        repl.handle_command("/limits turn_tokens 0")
        self.assertEqual(0, repl.max_turn_tokens)
        self.assertIn("disabled", out.getvalue())
        assembled.logger.close()

    def test_the_window_is_set_on_the_context_the_compactor_reads(self):
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("hi"))), "window")
        repl.handle_command("/limits window 12000")
        self.assertEqual(12000, assembled.context.context_window)
        assembled.logger.close()

    def test_a_bad_name_or_value_explains_itself(self):
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("hi"))), "bad")
        repl.handle_command("/limits nonsense 5")
        repl.handle_command("/limits turn_cost abc")
        repl.handle_command("/limits turn_cost -1")
        text = out.getvalue()
        self.assertIn("unknown limit", text)
        self.assertIn("needs a float", text)
        self.assertIn("negative", text)
        assembled.logger.close()


class TestContinueRecovers(unittest.TestCase):
    def test_continue_runs_a_turn_without_the_person_retyping(self):
        # The history is intact and the agent recorded why it stopped, so making
        # someone retype their instruction is a design failure.
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("carrying on"))), "continue")
        before = len(assembled.context.messages)
        repl.handle_command("/continue")
        self.assertGreater(len(assembled.context.messages), before)
        assembled.logger.close()

    def test_the_continuation_instruction_is_visible_in_the_history(self):
        # Providers need the last message to be a user turn and the wind-down
        # leaves an assistant message, so something must be added. It is written
        # into the transcript rather than injected invisibly.
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("carrying on"))), "visible")
        repl.handle_command("/continue")
        texts = [b.text for m in assembled.context.messages for b in m.content
                 if hasattr(b, "text")]
        self.assertTrue(any("Continue from where you stopped" in t for t in texts))
        assembled.logger.close()

    def test_continue_accepts_a_nudge(self):
        repl, out, assembled = build_repl(
            StubTransport(ok(end_turn("ok"))), "nudge")
        repl.handle_command("/continue head north instead")
        texts = [b.text for m in assembled.context.messages for b in m.content
                 if hasattr(b, "text")]
        self.assertIn("head north instead", texts)
        assembled.logger.close()
