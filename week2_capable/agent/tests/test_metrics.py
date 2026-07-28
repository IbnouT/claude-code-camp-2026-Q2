"""The four metrics through the real turn loop, and the cost ceiling.

Each metric answers a different question and none is derived from another, so the
tests drive the assembled chain and read what the loop recorded rather than
recomputing it here.
"""

import unittest

from boukensha.usage import amplification

from .helper import (
    RecordingLogger, StubTransport, add_ping_tool, build_agent, end_turn, ok,
    tool_use,
)


def cached_reply(text="done", fresh=100, read=900, write=0, out=20):
    return {"stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": fresh, "cache_read_input_tokens": read,
                      "cache_creation_input_tokens": write, "output_tokens": out}}


class TestTheLoopRecordsEachMetric(unittest.TestCase):
    def test_occupancy_is_the_whole_prompt_so_compaction_still_fires(self):
        # The precondition of the whole step: cached tokens still fill the window.
        agent, assembled = build_agent(
            StubTransport(ok(cached_reply(fresh=500, read=9000))),
            "occupancy", context_window=10_000)
        agent.run()
        ctx = assembled.context
        self.assertEqual(9500, ctx.current_tokens)
        self.assertTrue(ctx.needs_compaction())

    def test_volume_counts_every_class_so_caching_does_not_move_it(self):
        agent, cold = build_agent(
            StubTransport(ok(cached_reply(fresh=1000, read=0))), "cold_volume")
        agent.run()
        agent2, warm = build_agent(
            StubTransport(ok(cached_reply(fresh=100, read=900))), "warm_volume")
        agent2.run()
        self.assertEqual(cold.context.turn_tokens, warm.context.turn_tokens)

    def test_cost_is_recorded_per_class(self):
        agent, assembled = build_agent(
            StubTransport(ok(cached_reply(fresh=100, read=900))), "cost")
        agent.run()
        self.assertGreater(assembled.context.turn_cost, 0)

    def test_a_cached_turn_costs_less_than_the_same_work_uncached(self):
        agent, cold = build_agent(
            StubTransport(ok(cached_reply(fresh=1000, read=0))), "cold_cost")
        agent.run()
        agent2, warm = build_agent(
            StubTransport(ok(cached_reply(fresh=100, read=900))), "warm_cost")
        agent2.run()
        self.assertLess(warm.context.turn_cost, cold.context.turn_cost)

    def test_per_turn_quantities_reset(self):
        agent, assembled = build_agent(
            StubTransport(ok(cached_reply())), "reset")
        agent.run()
        self.assertGreater(assembled.context.turn_tokens, 0)
        assembled.context.reset_turn_tokens()
        self.assertEqual(0, assembled.context.turn_tokens)
        self.assertEqual(0.0, assembled.context.turn_cost)


class TestCostCeiling(unittest.TestCase):
    def test_the_cost_breaker_stops_the_turn_and_winds_down(self):
        log = RecordingLogger()
        # A tool_use call priced above a tiny ceiling, so the check opening the
        # next iteration trips on money rather than on tokens or steps.
        expensive = {"stop_reason": "tool_use",
                     "content": [{"type": "tool_use", "id": "t1", "name": "ping",
                                  "input": {}}],
                     "usage": {"input_tokens": 500_000, "output_tokens": 1000}}
        agent, _ = build_agent(
            StubTransport(ok(expensive), ok(end_turn("wound down"))),
            "cost_breaker", setup=add_ping_tool, logger=log,
            max_turn_cost=0.01, max_turn_tokens=0, max_iterations=25)
        text = agent.run()
        limits = log.kinds("limit_reached")
        self.assertTrue(limits, "the cost breaker never fired")
        self.assertEqual("max_cost", limits[0]["kind"])
        self.assertEqual("max_cost", log.kinds("turn_end")[-1]["reason"])
        self.assertTrue(text.strip())

    def test_zero_disables_the_cost_breaker(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(cached_reply(fresh=500_000, read=0, out=1000))),
            "cost_zero", logger=log, max_turn_cost=0)
        agent.run()
        self.assertEqual([], [k for k in log.kinds("limit_reached")
                              if k.get("kind") == "max_cost"])

    def test_an_unpriced_model_leaves_the_other_ceilings_guarding(self):
        # Cost cannot bind when rates are unknown: an unpriced call adds nothing
        # to the turn's cost, so the money ceiling never trips and the volume and
        # step ceilings are what stop a runaway turn. No boot failure is needed,
        # because a guard remains either way.
        log = RecordingLogger()
        agent, assembled = build_agent(
            StubTransport(ok(tool_use("ping", itok=50_000, otok=100))),
            "unpriced", setup=add_ping_tool, logger=log,
            max_turn_cost=0.01, max_turn_tokens=60_000, max_iterations=3)
        # An unpriced model is one whose catalog entry has no rates.
        assembled.backend._info = dict(assembled.backend._info,
                                       cost_per_million={"input": None,
                                                         "output": None})
        self.assertIsNone(assembled.backend.rates)
        agent.run()

        self.assertEqual(0.0, assembled.context.turn_cost,
                         "an unpriced model must not accrue a cost")
        kinds = [k["kind"] for k in log.kinds("limit_reached")]
        self.assertTrue(kinds, "nothing stopped the turn")
        self.assertNotIn("max_cost", kinds,
                         "the money ceiling cannot bind on an unpriced model")
        self.assertIn(kinds[0], ("max_tokens", "max_iterations"))


class TestAmplificationOverASession(unittest.TestCase):
    def test_repeated_prefixes_read_as_a_high_ratio(self):
        # Thirteen calls each re-sending the same ~3.2k prefix plus a little new
        # content is the shape a real session had, and it should read as roughly
        # ten to one rather than as a large bill with no stated cause.
        volume = 73_043
        unique = 7_000
        self.assertGreater(amplification(volume, unique), 5)


class TestAmplificationThroughTheLoop(unittest.TestCase):
    """Repetition measured from the session, not asserted from a constant."""

    def test_re_sending_the_same_history_raises_the_ratio(self):
        # Every call re-sends the whole conversation, so volume grows while
        # unique information barely does. That gap IS the metric.
        agent, assembled = build_agent(
            StubTransport(ok(tool_use("ping", itok=5000, otok=20)),
                          ok(end_turn("done", itok=5200, otok=20))),
            "amplify", setup=add_ping_tool, max_iterations=25)
        agent.run()
        ctx = assembled.context
        self.assertGreater(ctx.session_volume, 0)
        self.assertGreater(ctx.unique_tokens, 0)
        ratio = ctx.amplification()
        self.assertIsNotNone(ratio)
        self.assertGreater(ratio, 1.0,
                           "re-sent history must read as repetition")

    def test_the_prefix_counts_as_new_information_only_once(self):
        agent, assembled = build_agent(
            StubTransport(ok(cached_reply())), "prefix_once")
        agent.run()
        first = assembled.context.unique_tokens
        agent2, _ = build_agent(StubTransport(ok(cached_reply())), "prefix_once_2")
        agent2._context = assembled.context
        agent2.run()
        # The second turn adds its own messages but not the prefix again.
        self.assertLess(assembled.context.unique_tokens - first, first)

    def test_undefined_before_anything_is_sent(self):
        from boukensha.context import Context
        self.assertIsNone(Context("sys").amplification())
