"""The completeness rule, enforced against a fixture rather than against the writer.

EVERY FIELD THE LOGGER WRITES HAS A PLACE IN THE VIEWER. Testing that by importing
the writer would undo the independence this package exists to have, so the contract is
pinned as a FIXTURE instead: `fixtures/every_phase.jsonl`, produced once by the real
logger with every phase and every field populated, and checked in.

That gives both properties at once. The fixture is a genuine record, not a
hand-authored approximation of one, and the viewer needs nothing but the file to prove
it reads all of it. When the writer gains a field, regenerating the fixture is the
deliberate act that brings it into scope, and until then this test states exactly what
the viewer is known to handle.

The WRITER publishes it, which keeps the dependency pointing the right way. From the
agent step that owns the vocabulary:

    uv run python -m tests.make_fixture ../../log_viewer/tests/fixtures/every_phase.jsonl
"""

import json
import unittest
from pathlib import Path

from logviewer import (
    KNOWN_PHASES, cost_breakdown, group_turns, pair_tools, read, summarize,
    totals,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "every_phase.jsonl"

#: What the fixture is known to contain, per phase. A field the writer emits that
#: is not listed is not covered, and saying so is the point: this list is the
#: viewer's claim about what it handles, and it is checked against the file.
EXPECTED_FIELDS = {
    "session_start": ("schema", "model", "provider", "task", "system",
                      "context_window", "max_iterations", "max_output_tokens",
                      "max_turn_tokens", "rates", "caches", "cache_min_tokens"),
    # ``attempt`` appears only when a turn number is reused, which a healthy one-turn
    # fixture cannot contain. Covered where the behaviour lives, in test_pages.py for
    # the reader and in the writer's own suite for the record.
    "turn": ("n",),
    "iteration": ("n", "max"),
    "prompt": ("messages", "tools", "message_count", "tool_count",
               "context_window"),
    "plan": ("text",),
    "reasoning": ("text", "redacted"),
    "tool_call": ("name", "args", "id"),
    "tool_result": ("name", "result", "ok", "error", "tool_use_id"),
    "response": ("text", "usage", "stop_reason", "duration_ms", "model",
                 "provider", "cost_usd", "usage_unit", "context_window",
                 "input_tokens", "output_tokens"),
    "retry": ("attempt", "wait", "status", "error"),
    "compaction": ("before", "dropped", "compressed", "summarized",
                   "over_budget", "context_window", "trigger"),
    "limit_reached": ("kind", "n", "max"),
    "raw": ("data",),
    "turn_end": ("reason", "iterations", "tokens", "input_tokens",
                 "output_tokens", "cost_usd", "duration_ms", "usage",
                 "unique_tokens", "amplification"),
}


class TestTheFixtureIsWhatItClaims(unittest.TestCase):
    def setUp(self):
        self.result = read(FIXTURE)
        self.by_phase = {}
        for record in self.result.records:
            self.by_phase.setdefault(record.phase, []).append(record)

    def test_it_parses_completely(self):
        self.assertEqual(0, self.result.malformed)
        self.assertFalse(self.result.incomplete)
        self.assertGreater(len(self.result.records), 0)

    def test_every_phase_the_reader_knows_is_present(self):
        # log_error is emitted only when the writer itself fails, so a healthy
        # session cannot contain one and the fixture is a healthy session.
        expected = set(KNOWN_PHASES) - {"log_error"}
        missing = sorted(expected - set(self.by_phase))
        self.assertEqual([], missing, f"the fixture is missing: {missing}")

    def test_every_claimed_field_is_actually_in_the_fixture(self):
        problems = []
        for phase, fields in EXPECTED_FIELDS.items():
            records = self.by_phase.get(phase)
            if not records:
                problems.append(f"{phase}: absent")
                continue
            present = set()
            for record in records:
                present |= set(record.data)
            for field in fields:
                if field not in present:
                    problems.append(f"{phase}.{field}")
        self.assertEqual([], problems, f"claimed but not present: {problems}")

    def test_nothing_in_the_fixture_is_unclaimed(self):
        """The other direction, which is the one that catches a new field.

        A field appearing in the log that this file does not list is a field the
        viewer has not been shown to handle. Failing here is the intended
        behaviour: it forces the addition to be noticed.
        """
        universal = {"phase", "at", "session_id"}
        unclaimed = {}
        for phase, records in self.by_phase.items():
            claimed = set(EXPECTED_FIELDS.get(phase, ())) | universal
            present = set()
            for record in records:
                present |= set(record.data)
            extra = sorted(present - claimed)
            if extra:
                unclaimed[phase] = extra
        self.assertEqual({}, unclaimed, f"fields nothing claims: {unclaimed}")


class TestTheReaderDerivesWhatAViewerAsks(unittest.TestCase):
    """The fixture read through every derivation, so none of them raise on it."""

    def setUp(self):
        self.records = read(FIXTURE).records

    def test_the_session_summarizes(self):
        summary = summarize(FIXTURE)
        self.assertEqual(1, summary.turns)
        self.assertEqual("max_tokens", summary.outcome)
        self.assertIsNotNone(summary.model)
        # Priced, because the fixture came from a run with a real backend. A
        # session with no rates would read "unavailable" here, and that path has
        # its own test in test_sessions.py.
        self.assertIn("$", summary.render_cost())

    def test_the_turn_carries_the_figures_the_writer_recorded(self):
        turn = group_turns(self.records)[0]
        self.assertEqual("max_tokens", turn.reason)
        self.assertTrue(turn.tripped)
        # Read from the record, never re-summed. The prompt total is the three
        # input classes, which is the invariant rather than a literal figure the
        # fixture happens to carry.
        self.assertGreater(turn.tokens, 0)
        self.assertIsNotNone(turn.cost)
        self.assertGreater(turn.amplification, 1.0)
        self.assertGreater(turn.unique_tokens, 0)
        self.assertEqual(turn.input_tokens,
                         turn.usage["fresh_input"] + turn.usage["cache_read"]
                         + turn.usage["cache_write"])
        self.assertEqual(turn.output_tokens, turn.usage["output"])

    def test_a_failing_tool_result_is_readable_even_unpaired(self):
        # The fixture carries a failed result whose call is not in the log, which
        # is the case a viewer must not drop: an unmatched half is usually the
        # thing being investigated.
        failures = [r for r in self.records
                    if r.phase == "tool_result" and not r.get("ok")]
        self.assertEqual(1, len(failures))
        self.assertEqual("blocked exit", failures[0].get("error"))
        pairs = pair_tools(self.records)
        self.assertTrue(pairs)
        for call, _result in pairs:
            self.assertIsNotNone(call.get("name"))

    def test_trouble_is_visible_without_hunting(self):
        trouble = [r.phase for r in self.records if r.trouble]
        for phase in ("tool_result", "retry", "limit_reached"):
            self.assertIn(phase, trouble)

    def test_the_totals_and_the_breakdown_hold(self):
        figures = totals(self.records)
        self.assertEqual(2, figures["calls"])
        self.assertEqual(1, figures["compactions"])
        self.assertEqual([1], figures["tripped"])
        self.assertGreater(figures["failures"], 0)
        rows = cost_breakdown(self.records)
        self.assertEqual(1, len(rows))
        self.assertNotEqual("unknown", rows[0]["provider"])
        self.assertTrue(rows[0]["cost_known"])

    def test_the_prompt_payload_is_present_for_the_context_diff(self):
        prompts = [r for r in self.records if r.phase == "prompt"]
        self.assertTrue(prompts)
        messages = prompts[0].get("messages")
        self.assertEqual(prompts[0].get("message_count"), len(messages))
        self.assertIn("bakery", json.dumps(messages))


if __name__ == "__main__":
    unittest.main()
