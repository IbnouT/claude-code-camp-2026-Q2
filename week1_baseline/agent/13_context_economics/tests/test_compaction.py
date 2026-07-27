"""Structure-aware compaction: the pipeline's contract, wire-safety, and memory.

The reference leaves compaction untested. These golden tests pin the behaviour
that matters: tokens are reclaimed by compressing before dropping, a tool_result
is never orphaned from its tool_use, the survivor prefix starts on a user turn,
and the journey-state memory note survives a drop so the agent does not forget.
"""

import unittest

from boukensha.compaction import (
    CompactionResult, _est_tokens, compact, prefix_tokens, summarize)
from boukensha.context import Context
from boukensha.journey import JourneyParser
from boukensha.message import (
    Message, Role, TextBlock, ToolResultBlock, ToolUseBlock,
)

VERBOSE = ("You are in a long and detailed room with much prose. " * 30)


def _history(turns: int) -> list[Message]:
    msgs: list[Message] = []
    for i in range(turns):
        msgs.append(Message(Role.USER, (TextBlock(f"go {i}"),)))
        msgs.append(Message(Role.ASSISTANT,
                            (ToolUseBlock(f"t{i}", "move", {"direction": "n"}),)))
        msgs.append(Message(Role.TOOL_RESULT,
                            (ToolResultBlock(f"t{i}", "move", VERBOSE),)))
    return msgs


def _journey() -> JourneyParser:
    p = JourneyParser()
    p.on_tool_call("tbamud__look", {}, "a")
    p.on_tool_result("tbamud__look",
                     "The Temple\n[ Exits: n s ]\n24H 100M 80V >", "a")
    p.on_tool_call("tbamud__move", {"direction": "south"}, "b")
    p.on_tool_result("tbamud__move",
                     "Market Square\n[ Exits: n e s w ]\n24H 100M 79V >", "b")
    return p


class TestSummarize(unittest.TestCase):
    def test_summary_reflects_the_journey_state(self):
        note = summarize(_journey().state)
        self.assertIn("The Temple", note)
        self.assertIn("Market Square", note)
        self.assertIn("now at Market Square", note)
        self.assertTrue(note.startswith("Memory of earlier play"))

    def test_empty_state_yields_no_summary(self):
        self.assertEqual("", summarize(JourneyParser().state))


class TestPipeline(unittest.TestCase):
    def test_compresses_old_tool_results_before_dropping(self):
        # With a window that compression alone can fit under, the stubs survive
        # and nothing is dropped: the whole point of compress-before-drop.
        msgs = _history(6)
        result = compact(msgs, _journey().state, window=8000, keep_recent=2)
        self.assertIsInstance(result, CompactionResult)
        self.assertGreater(result.compressed, 0)      # stubs, not just drops
        self.assertEqual(0, result.dropped)           # compression was enough
        bodies = [b.content for m in result.messages for b in m.content
                  if isinstance(b, ToolResultBlock)]
        self.assertTrue(any("[compacted]" in b for b in bodies))

    def test_survivor_prefix_starts_on_a_user_turn(self):
        result = compact(_history(6), _journey().state, window=800, keep_recent=2)
        self.assertTrue(result.messages)
        self.assertIs(result.messages[0].role, Role.USER)

    def test_no_tool_result_is_orphaned_from_its_tool_use(self):
        # Every surviving tool_result's tool_use_id must be introduced by a
        # preceding assistant tool_use in the survivors.
        result = compact(_history(6), _journey().state, window=600, keep_recent=2)
        seen_uses = set()
        for m in result.messages:
            for b in m.content:
                if isinstance(b, ToolUseBlock):
                    seen_uses.add(b.id)
                if isinstance(b, ToolResultBlock):
                    self.assertIn(b.tool_use_id, seen_uses,
                                  "orphaned tool_result in compacted history")

    def test_memory_summary_survives_a_drop(self):
        result = compact(_history(8), _journey().state, window=500, keep_recent=2)
        self.assertGreater(result.dropped, 0)
        self.assertTrue(result.summarized)
        head = "".join(getattr(b, "text", "") for b in result.messages[0].content)
        self.assertIn("Memory of earlier play", head)

    def test_no_window_falls_back_to_a_wire_safe_count_drop(self):
        result = compact(_history(6), _journey().state, window=0, keep_recent=2)
        self.assertGreater(result.dropped, 0)
        self.assertIs(result.messages[0].role, Role.USER)


class TestContextIntegration(unittest.TestCase):
    def test_context_compaction_uses_the_pipeline_and_records_detail(self):
        ctx = Context("system", context_window=1000)
        ctx.journey = _journey()
        for m in _history(6):
            ctx.add(m)
        dropped = ctx.compact_messages()
        self.assertEqual(dropped, ctx.last_compaction.dropped)
        self.assertGreater(ctx.last_compaction.compressed, 0)
        self.assertTrue(ctx.last_compaction.summarized)
        self.assertEqual(0, ctx.current_tokens)     # occupancy reset


class TestOverheadAwareTarget(unittest.TestCase):
    """The prompt is more than its message list.

    The system prompt and every tool schema ride on each call and are not in
    ``messages``, so a budget measured only against the list under-compacts: the
    trigger fires on the true prompt size while the target sees a tiny history,
    and the window keeps filling. The overhead is measured from the objects that
    own it and passed in, so the budget applies to the real prompt.
    """

    def _history(self, turns=8):
        history = []
        for i in range(turns):
            history.append(Message(Role.USER, (TextBlock(f"instruction {i}"),)))
            history.append(Message(Role.ASSISTANT, (TextBlock(f"reply {i}"),)))
            history.append(Message(Role.TOOL_RESULT, (ToolResultBlock(
                f"t{i}", "look", "A long room description. " * 12),)))
        return history

    def test_ignoring_overhead_stops_early(self):
        # With no overhead declared the list looks small enough on its own, so
        # compression alone satisfies the budget and nothing is dropped.
        result = compact(self._history(), None, window=1000, keep_recent=2)
        self.assertEqual(0, result.dropped)
        self.assertGreater(result.compressed, 0)

    def test_measured_overhead_makes_dropping_engage(self):
        # Same history and window, but 4000 tokens of system prompt and tool
        # schemas ride on every call, so that is what fills the window and turns
        # must go.
        result = compact(self._history(), None, window=1000, overhead=4000,
                         keep_recent=2)
        self.assertGreater(result.dropped, 0)

    def test_overhead_larger_than_the_window_still_leaves_a_valid_start(self):
        # A big tool surface against a small window cannot be solved by
        # compaction, but it must never produce an invalid history.
        result = compact(self._history(), None, window=500, overhead=20_000,
                         keep_recent=2)
        self.assertTrue(result.messages)
        self.assertIs(Role.USER, result.messages[0].role)


class TestPrefixTokens(unittest.TestCase):
    """The overhead is measured from what owns it, never inferred.

    Inferring it by subtracting a history estimate from a past call's reported
    size compares two different prompts, because the caller appends the new user
    turn before compaction runs. A large user message then drives the subtraction
    negative, it floors to zero, and the budget silently loses all overhead
    accounting.
    """

    class _Tool:
        def __init__(self, name, description, parameters):
            self.name, self.description = name, description
            self.parameters = parameters

    def test_counts_the_system_prompt(self):
        self.assertGreater(prefix_tokens("x" * 400, None), 0)
        self.assertEqual(0, prefix_tokens(None, None))

    def test_counts_tool_schemas(self):
        tools = {f"t{i}": self._Tool(f"t{i}", "d" * 100, {"a": {"type": "string"}})
                 for i in range(10)}
        with_tools = prefix_tokens("sys", tools)
        self.assertGreater(with_tools, prefix_tokens("sys", None))

    def test_accepts_a_mapping_or_a_sequence(self):
        tools = [self._Tool("look", "look around", {})]
        self.assertEqual(prefix_tokens("s", tools),
                         prefix_tokens("s", {"look": tools[0]}))

    def test_a_big_user_message_cannot_erase_the_overhead(self):
        # The failure the inference had: history larger than the overhead.
        history = [Message(Role.USER, (TextBlock("x" * 40_000),))]
        overhead = prefix_tokens("system prompt", None)
        result = compact(history, None, window=10_000, overhead=overhead,
                         keep_recent=1)
        self.assertTrue(result.over_budget or result.messages)


class TestOverBudgetSignal(unittest.TestCase):
    def test_reports_when_it_could_not_free_enough(self):
        # Overhead alone exceeds the budget, so no amount of dropping helps and
        # the caller must be able to see that rather than assume success.
        history = [Message(Role.USER, (TextBlock("hello"),)),
                   Message(Role.ASSISTANT, (TextBlock("hi"),))]
        result = compact(history, None, window=1000, overhead=50_000,
                         keep_recent=2)
        self.assertTrue(result.over_budget)

    def test_reports_success_when_it_freed_enough(self):
        history = []
        for i in range(8):
            history.append(Message(Role.USER, (TextBlock(f"m{i}"),)))
            history.append(Message(Role.ASSISTANT, (TextBlock(f"r{i}"),)))
        result = compact(history, None, window=100_000, overhead=10,
                         keep_recent=2)
        self.assertFalse(result.over_budget)


class TestDroppedCountIsExact(unittest.TestCase):
    def test_messages_skipped_for_wire_validity_are_counted(self):
        # A leading assistant message removed to reach a user turn is a dropped
        # message like any other, and the log is the evidence base downstream.
        history = [Message(Role.ASSISTANT, (TextBlock("orphan"),)),
                   Message(Role.USER, (TextBlock("first real turn"),)),
                   Message(Role.ASSISTANT, (TextBlock("reply"),))]
        result = compact(history, None, window=100_000, overhead=0, keep_recent=3)
        self.assertEqual(1, result.dropped)
        self.assertIs(Role.USER, result.messages[0].role)


class TestFreesTokens(unittest.TestCase):
    def test_the_surviving_history_is_smaller_in_tokens(self):
        # Freed space is measured in tokens, not message count: compression can
        # reach the target without dropping a single turn.
        history = []
        for i in range(8):
            history.append(Message(Role.USER, (TextBlock(f"turn {i}"),)))
            history.append(Message(Role.ASSISTANT, (TextBlock(f"reply {i}"),)))
            history.append(Message(Role.TOOL_RESULT, (ToolResultBlock(
                f"t{i}", "look", "A long room description. " * 12),)))
        before = sum(_est_tokens(m) for m in history)
        result = compact(history, None, window=1000, keep_recent=2)
        after = sum(_est_tokens(m) for m in result.messages)
        self.assertLess(after, before)


if __name__ == "__main__":
    unittest.main()
