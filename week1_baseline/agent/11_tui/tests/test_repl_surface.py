"""The Repl surface a front-end drives: routing, readers, cancellation."""

import threading
import unittest

from boukensha.errors import TurnCancelled
from boukensha.repl import Repl

from .helper import StubTransport, build_repl, end_turn, ok


class TestClassifyInput(unittest.TestCase):
    def test_a_slash_word_is_a_command(self):
        self.assertEqual(("command", "/help"), Repl.classify_input("/help"))

    def test_a_double_slash_is_an_in_character_turn(self):
        # One slash dropped: the agent receives a literal /say line.
        self.assertEqual(("turn", "/say hi"), Repl.classify_input("//say hi"))

    def test_plain_text_is_a_turn(self):
        self.assertEqual(("turn", "go north"), Repl.classify_input("go north"))


class TestReaders(unittest.TestCase):
    def test_turn_reader_reflects_undo(self):
        # /undo decrements the REAL counter, so a front-end reading the property
        # can never drift the way a shadow count would.
        repl, _ = build_repl(StubTransport(ok(end_turn("hi"))), "readers_undo")
        repl.run_turn("hello")
        self.assertEqual(1, repl.turn)
        repl.handle_command("/undo")
        self.assertEqual(0, repl.turn)

    def test_tokens_and_cost_accumulate_from_turns(self):
        repl, _ = build_repl(
            StubTransport(ok(end_turn("hi", itok=1000, otok=40))), "readers_cost")
        repl.run_turn("hello")
        self.assertEqual(1000, repl.tokens_in)
        self.assertEqual(40, repl.tokens_out)
        self.assertGreater(repl.cost, 0.0)

    def test_commands_is_a_read_only_table(self):
        repl, _ = build_repl(StubTransport(ok(end_turn("x"))), "readers_commands")
        names = [c.name for c in repl.commands]
        self.assertIn("/help", names)
        self.assertIn("/exit", names)
        self.assertIsInstance(repl.commands, tuple)


class TestCancellation(unittest.TestCase):
    def test_cancel_turn_is_false_when_idle(self):
        repl, _ = build_repl(StubTransport(ok(end_turn("x"))), "cancel_idle")
        self.assertFalse(repl.cancel_turn())

    def test_a_pre_set_event_cancels_before_the_model_call(self):
        # The agent checks the event at the top of every iteration, so a set
        # event means no request is ever made.
        from boukensha.agent import Agent
        from boukensha.tasks import Player

        transport = StubTransport(ok(end_turn("never")))
        repl, asm = build_repl(transport, "cancel_preset")
        event = threading.Event()
        event.set()
        agent = Agent(asm.context, asm.registry, asm.builder, asm.client,
                      task=Player, task_settings=asm.task_settings,
                      cancel_event=event, logger=asm.logger)
        from boukensha.message import Message
        asm.context.add(Message.user("hello"))
        with self.assertRaises(TurnCancelled):
            agent.run()
        self.assertEqual(0, len(transport.calls))

    def test_a_cancelled_turn_keeps_history_well_formed(self):
        # run_turn records a synthetic assistant note on cancellation, so the
        # next request never carries a user message with no reply. Whether the
        # cancel lands before or after the reply, pairs stay balanced.
        repl, asm = build_repl(StubTransport(ok(end_turn("x"))), "cancel_history")
        canceller = threading.Thread(
            target=lambda: any(repl.cancel_turn() for _ in range(200)),
            daemon=True)
        canceller.start()
        repl.run_turn("hello")
        canceller.join(timeout=2)
        roles = [m.role.value for m in asm.context.messages]
        self.assertEqual(0, len(roles) % 2)
        self.assertEqual("assistant", roles[-1])
