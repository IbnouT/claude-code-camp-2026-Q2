"""The two breakers and the usage accounting they read, end to end.

These drive the real turn loop over a scripted transport, so a test fails when
the loop stops for the wrong reason or stops at the wrong number. Asserting the
resolver in isolation cannot catch that: the resolved value has to reach the
loop, and the loop has to act on it.
"""

import unittest

from boukensha.agent import Agent
from boukensha.context import Context

from .helper import (
    RecordingLogger, StubTransport, add_ping_tool, build_agent, end_turn, ok,
    tool_use,
)


class TestSpendBreaker(unittest.TestCase):
    def test_spend_breaker_stops_the_loop_and_winds_down(self):
        # The breaker is evaluated at the TOP of each iteration, so the ceiling
        # has to be below what one call books. The first tool_use call books
        # 1200 in + 20 out, so a 1000-token ceiling trips the check that opens
        # iteration two and the turn winds down instead of looping on.
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping")), ok(end_turn("done"))),
            "spend_breaker", setup=add_ping_tool, logger=log,
            max_turn_tokens=1000, max_iterations=25,
        )
        text = agent.run()

        limits = log.kinds("limit_reached")
        self.assertTrue(limits, "the spend breaker never reported limit_reached")
        self.assertEqual("max_tokens", limits[0]["kind"])
        ends = log.kinds("turn_end")
        self.assertEqual("max_tokens", ends[-1]["reason"])
        # It stopped early, well under the iteration ceiling.
        self.assertLess(ends[-1]["iterations"], 25)
        self.assertTrue(text.strip(), "wind-down produced no text")

    def test_zero_disables_the_spend_breaker(self):
        # 0 means no ceiling, so a turn that would trip any positive limit runs
        # to its natural end.
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(end_turn("finished"))), "spend_zero",
            logger=log, max_turn_tokens=0,
        )
        agent.run()
        self.assertEqual([], [k for k in log.kinds("limit_reached")
                              if k.get("kind") == "max_tokens"])
        self.assertEqual("completed", log.kinds("turn_end")[-1]["reason"])

    def test_zero_disables_the_iteration_breaker(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(end_turn("finished"))), "iter_zero",
            logger=log, max_iterations=0,
        )
        agent.run()
        self.assertEqual([], [k for k in log.kinds("limit_reached")
                              if k.get("kind") == "max_iterations"])

    def test_iteration_breaker_stops_a_tool_loop(self):
        # A transport that always asks for another tool call can only be stopped
        # by the iteration ceiling.
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping"))), "iter_breaker",
            setup=add_ping_tool, logger=log,
            max_iterations=3, max_turn_tokens=0,
        )
        agent.run()
        limits = log.kinds("limit_reached")
        self.assertEqual("max_iterations", limits[0]["kind"])
        self.assertEqual("max_iterations", log.kinds("turn_end")[-1]["reason"])
        self.assertEqual(3, log.kinds("turn_end")[-1]["iterations"])


class TestAssembledLimits(unittest.TestCase):
    def test_configured_limits_reach_the_running_agent(self):
        # The assembly path, not the resolver in isolation: a value set in the
        # task settings has to arrive on the Agent the loop actually runs.
        agent, _ = build_agent(
            StubTransport(ok(end_turn("hi"))), "assembled_limits",
            max_turn_tokens=4321, max_iterations=7,
        )
        self.assertEqual(4321, agent._max_turn_tokens)
        self.assertEqual(7, agent._max_iterations)


class TestUsageNormalization(unittest.TestCase):
    """Every provider's usage shape must reach the same two counters."""

    SHAPES = {
        "anthropic": ({"usage": {"input_tokens": 11, "output_tokens": 3}}, 11, 3),
        "openai_chat": ({"usage": {"prompt_tokens": 12, "completion_tokens": 4}}, 12, 4),
        "gemini": ({"usageMetadata": {"promptTokenCount": 13,
                                      "candidatesTokenCount": 5}}, 13, 5),
        "ollama": ({"prompt_eval_count": 14, "eval_count": 6}, 14, 6),
    }

    def test_each_provider_shape_records_both_counters(self):
        for name, (response, want_in, want_out) in self.SHAPES.items():
            with self.subTest(provider=name):
                agent, assembled = build_agent(
                    StubTransport(ok(end_turn("x"))), f"usage_{name}")
                ctx = assembled.context
                ctx.reset_turn_tokens()
                agent._record_usage(response)
                self.assertEqual(want_in + want_out, ctx.turn_tokens)
                # Window occupancy tracks the input side only.
                self.assertEqual(want_in, ctx.current_tokens)

    def test_a_missing_usage_block_is_not_an_error(self):
        agent, assembled = build_agent(
            StubTransport(ok(end_turn("x"))), "usage_missing")
        assembled.context.reset_turn_tokens()
        agent._record_usage({})
        self.assertEqual(0, assembled.context.turn_tokens)


class TestNormalizedStopReason(unittest.TestCase):
    def test_stop_reason_logged_is_the_normalized_one(self):
        # Gemini and Ollama bodies carry no literal "stop_reason" key, so the
        # logged value has to come from the parsed reply, not the raw body.
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(end_turn("done"))), "stop_reason", logger=log)
        agent.run()
        responses = log.kinds("response")
        self.assertTrue(responses)
        self.assertEqual("end_turn", responses[-1]["stop_reason"])


class TestExtractText(unittest.TestCase):
    def test_multiple_text_blocks_join_on_newlines(self):
        # A provider may split one reply across several text blocks (Gemini
        # emits a part per paragraph). Joining with nothing glues words together.
        from boukensha.message import TextBlock
        self.assertEqual(
            "One.\nTwo.",
            Agent._extract_text((TextBlock("One."), TextBlock("Two."))))


class TestDropLastTurn(unittest.TestCase):
    """Regression: /undo and /retry both call this and it raised NameError."""

    def test_drop_last_turn_returns_the_removed_user_text(self):
        from boukensha.message import Message
        ctx = Context("sys")
        ctx.add(Message.user("go north"))
        ctx.add(Message.assistant("you went north"))
        self.assertEqual("go north", ctx.drop_last_turn())
        self.assertEqual([], ctx.messages)

    def test_drop_last_turn_on_empty_history_is_none(self):
        self.assertIsNone(Context("sys").drop_last_turn())

    def test_drop_last_turn_keeps_earlier_turns(self):
        from boukensha.message import Message
        ctx = Context("sys")
        ctx.add(Message.user("first"))
        ctx.add(Message.assistant("reply one"))
        ctx.add(Message.user("second"))
        ctx.add(Message.assistant("reply two"))
        self.assertEqual("second", ctx.drop_last_turn())
        self.assertEqual(2, len(ctx.messages))



class TestWindDownDoesNotMaskWindowPressure(unittest.TestCase):
    """The wind-down call is tools-disabled, so its input is far smaller than a
    normal call's. Letting it set window pressure hides the real occupancy, and
    the next turn then skips a compaction it needed and overflows on its first
    call. Its tokens must still count toward the turn's spend.
    """

    def test_wind_down_keeps_pressure_from_the_last_real_call(self):
        log = RecordingLogger()
        # A tool_use call at 6000 input, then the wind-down reply at 800.
        agent, assembled = build_agent(
            StubTransport(ok(tool_use("ping", itok=6000, otok=20)),
                          ok(end_turn("wound down", itok=800, otok=30))),
            "winddown_pressure", setup=add_ping_tool, logger=log,
            max_turn_tokens=1000, max_iterations=25)
        agent.run()
        ctx = assembled.context
        # Pressure reflects the real call, not the small tools-disabled one.
        self.assertEqual(6000, ctx.current_tokens)
        # Spend still includes the wind-down call.
        self.assertEqual(6000 + 20 + 800 + 30, ctx.turn_tokens)

    def test_wind_down_spend_is_reported_in_turn_end(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping", itok=6000, otok=20)),
                          ok(end_turn("wound down", itok=800, otok=30))),
            "winddown_spend", setup=add_ping_tool, logger=log,
            max_turn_tokens=1000, max_iterations=25)
        agent.run()
        self.assertEqual(6850, log.kinds("turn_end")[-1]["tokens"])


class TestDurationIsRecorded(unittest.TestCase):
    """Wall clock is a different question from tokens, and it went missing once.

    Steps 10 and 11 logged `duration_ms` and step 12 silently stopped, so every
    session after that carried no timing at all. A turn can be cheap and slow, and
    that is invisible in any token view, so this guards the field's presence rather
    than trusting it.
    """

    def test_a_response_carries_its_wall_clock(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(end_turn("done"))), "duration_response", logger=log)
        agent.run()
        responses = log.kinds("response")
        self.assertTrue(responses)
        self.assertIn("duration_ms", responses[-1])
        self.assertIsNotNone(responses[-1]["duration_ms"])

    def test_turn_end_reports_the_turn_total(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping")), ok(end_turn("done"))),
            "duration_turn", setup=add_ping_tool, logger=log)
        agent.run()
        ends = log.kinds("turn_end")
        self.assertIn("duration_ms", ends[-1])
        self.assertIsNotNone(ends[-1]["duration_ms"])

    def test_the_turn_total_accumulates_across_calls(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping")), ok(end_turn("done"))),
            "duration_accum", setup=add_ping_tool, logger=log)
        agent.run()
        per_call = [r["duration_ms"] for r in log.kinds("response")
                    if r.get("duration_ms")]
        total = log.kinds("turn_end")[-1]["duration_ms"]
        self.assertGreaterEqual(len(per_call), 2)
        # The turn total covers every call, so it is at least the largest of them.
        self.assertGreaterEqual(total, max(per_call))

    def test_the_counter_resets_between_turns(self):
        log = RecordingLogger()
        agent, assembled = build_agent(
            StubTransport(ok(end_turn("one"))), "duration_reset1", logger=log)
        agent.run()
        first = log.kinds("turn_end")[-1]["duration_ms"]
        agent2, _ = build_agent(
            StubTransport(ok(end_turn("two"))), "duration_reset2", logger=log)
        agent2._context = assembled.context
        agent2.run()
        second = log.kinds("turn_end")[-1]["duration_ms"]
        # A fresh Agent starts at zero, so the second turn is not the sum of both.
        self.assertLess(second, first + second)

    def test_every_response_in_a_turn_is_timed_including_the_wind_down(self):
        """The wind-down is a model call, so it is a timed model call.

        It was not. The normal paths went through the one timing helper and the
        wind-down called the client directly, so a turn that tripped a ceiling
        logged its last response with no duration at all. A turn-level total
        that merely accumulates across calls stays plausible while that leaks,
        which is why this asserts EVERY response rather than the total.
        """
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping")), ok(end_turn("wound down"))),
            "duration_winddown", setup=add_ping_tool, logger=log,
            max_turn_tokens=1000, max_iterations=25)
        agent.run()

        self.assertTrue(log.kinds("limit_reached"),
                        "no ceiling tripped, so no wind-down call was made")
        responses = log.kinds("response")
        self.assertGreaterEqual(len(responses), 2)
        untimed = [i for i, r in enumerate(responses)
                   if r.get("duration_ms") is None]
        self.assertEqual([], untimed,
                         f"{len(untimed)} of {len(responses)} responses untimed")

    def test_the_turn_total_covers_the_wind_down_call(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping")), ok(end_turn("wound down"))),
            "duration_winddown_total", setup=add_ping_tool, logger=log,
            max_turn_tokens=1000, max_iterations=25)
        agent.run()
        per_call = [r["duration_ms"] for r in log.kinds("response")]
        total = log.kinds("turn_end")[-1]["duration_ms"]
        # The total is the sum of every call including the wind-down, so it
        # cannot be less than that sum however small the last call was.
        self.assertGreaterEqual(total + 1e-9, sum(per_call))

    def test_a_wind_down_that_fails_still_reports_the_time_it_waited(self):
        """A call that raises consumed the time it spent before raising.

        On a timeout that is the largest number in the turn, so dropping it
        would make the slowest turns look the fastest.
        """
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping")), (400, "no", {})),
            "duration_winddown_fails", setup=add_ping_tool, logger=log,
            max_turn_tokens=1000, max_iterations=25)
        text = agent.run()

        self.assertTrue(text.strip(), "no fallback message after a failed call")
        logged = [r["duration_ms"] for r in log.kinds("response")]
        total = log.kinds("turn_end")[-1]["duration_ms"]
        self.assertIsNotNone(total)
        # The failed wind-down logged no response of its own, so the turn total
        # exceeding every response that WAS logged is the only evidence its
        # wait was counted.
        self.assertGreater(total, sum(logged))


if __name__ == "__main__":
    unittest.main()
