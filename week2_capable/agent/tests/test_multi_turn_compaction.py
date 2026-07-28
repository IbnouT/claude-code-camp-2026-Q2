"""A multi-turn session compacts itself, driven through the real chain.

This is the deterministic proof that used to live in the example. Compaction is
evaluated at the start of a turn, so it can only be shown across turns, and the
whole assembly (Context, Registry, PromptBuilder, Client, Logger, Agent) runs over
a scripted transport so the behaviour is exercised with no network and no key.
"""

import unittest

from boukensha.compaction import prefix_tokens

from .helper import (
    RecordingLogger, StubTransport, add_ping_tool, build_agent, end_turn, ok,
    tool_use,
)


class TestCompactionAcrossTurns(unittest.TestCase):
    def test_a_second_turn_compacts_after_the_first_fills_the_window(self):
        # A 1000-token window with a call reporting 900 input puts occupancy at
        # 90 percent, above the 0.85 threshold, so the next turn must compact
        # before it calls.
        log = RecordingLogger()
        agent, assembled = build_agent(
            StubTransport(ok(end_turn("first reply", itok=900, otok=20))),
            "multi_turn", logger=log, context_window=1000)
        ctx = assembled.context

        agent.run()                                  # turn one fills the window
        self.assertTrue(ctx.needs_compaction(),
                        "the first turn should have left the window over threshold")
        self.assertEqual([], log.kinds("compaction"),
                         "nothing should compact before a second turn opens")

        # A fresh Agent over the same Context is exactly what the REPL does.
        agent2, _ = build_agent(
            StubTransport(ok(end_turn("second reply", itok=100, otok=10))),
            "multi_turn_2", logger=log, context_window=1000)
        agent2._context = ctx
        agent2.run()

        events = log.kinds("compaction")
        self.assertTrue(events, "the second turn did not compact")
        self.assertEqual(1000, events[0]["context_window"])
        self.assertGreaterEqual(events[0]["before"], 850)

    def test_compaction_resets_occupancy_so_it_does_not_fire_forever(self):
        log = RecordingLogger()
        agent, assembled = build_agent(
            StubTransport(ok(end_turn("reply", itok=900, otok=20))),
            "reset_occupancy", logger=log, context_window=1000)
        ctx = assembled.context
        agent.run()
        ctx.compact_messages(overhead=prefix_tokens(ctx.system, None))
        self.assertFalse(ctx.needs_compaction(),
                         "occupancy must reset, or every later turn compacts")


if __name__ == "__main__":
    unittest.main()
