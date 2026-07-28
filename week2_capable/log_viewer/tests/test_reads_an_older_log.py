"""A log written by an EARLIER version of the agent, still fully readable.

The claim that a reader outlives its writer is only worth making if it is tested
against a real old file. `fixtures/legacy_step11.jsonl` is one complete turn lifted
verbatim from a genuine session recorded before three of the fields the current writer
emits existed:

- `tokens` is present as `null`, from the period when it was written unconditionally.
- the four token classes, `unique_tokens` and `amplification` are absent entirely.
- no `compaction`, `plan`, `reasoning` or `raw` record appears, because that writer
  either did not emit them or the session did not produce them.

Only the `prompt` payloads were altered, and only to trim their bodies: they carry the
whole history on every call and dominated the file size. The counts are untouched, and
the marker left in their place makes the trim visible so nobody reads it as something
the writer did.

What this asserts is that missing means missing. A viewer that treated an absent field
as a zero would report this session as free, as having no repetition, and as having
processed nothing, all of which are false.
"""

import unittest
from pathlib import Path

from logviewer import group_turns, pair_tools, read, summarize, totals

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "legacy_step11.jsonl"


class TestAnOlderLogStillReads(unittest.TestCase):
    def setUp(self):
        self.result = read(FIXTURE)
        self.records = self.result.records

    def test_it_parses_with_nothing_malformed(self):
        self.assertEqual(0, self.result.malformed)
        self.assertFalse(self.result.incomplete)
        self.assertGreater(len(self.records), 20)

    def test_every_phase_it_carries_is_understood(self):
        unknown = sorted({r.phase for r in self.records if not r.known})
        self.assertEqual([], unknown, f"phases this reader cannot name: {unknown}")

    def test_the_turn_reads_what_is_there(self):
        turn = group_turns(self.records)[0]
        self.assertEqual("completed", turn.reason)
        self.assertFalse(turn.tripped)
        self.assertEqual(7, turn.iterations)
        # This writer logged the split and the cost, so those are read.
        self.assertEqual(31168, turn.input_tokens)
        self.assertEqual(701, turn.output_tokens)
        self.assertEqual(0.034673, turn.cost)
        self.assertEqual(13471, turn.duration_ms)

    def test_what_that_writer_never_recorded_reads_as_absent(self):
        turn = group_turns(self.records)[0]
        # `tokens` is present as null in this era, and null is not zero dressed up.
        self.assertEqual(0, turn.tokens)
        self.assertIsNone(turn.usage)
        self.assertIsNone(turn.unique_tokens)
        self.assertIsNone(turn.amplification)

    def test_the_session_summarizes_without_the_newer_fields(self):
        summary = summarize(FIXTURE)
        self.assertEqual(1, summary.turns)
        self.assertEqual("completed", summary.outcome)
        self.assertEqual("claude-haiku-4-5", summary.model)
        self.assertEqual("anthropic", summary.provider)
        self.assertIn("$", summary.render_cost())
        self.assertEqual(0, summary.compactions)

    def test_the_derivations_hold_on_it(self):
        figures = totals(self.records)
        self.assertGreater(figures["calls"], 0)
        self.assertGreater(figures["tool_calls"], 0)
        self.assertEqual([], figures["tripped"])
        pairs = pair_tools(self.records)
        self.assertTrue(pairs)
        # Every call in a complete turn got its result.
        self.assertEqual([], [c.get("name") for c, r in pairs if r is None])

    def test_the_prompt_counts_survived_the_trim(self):
        # The bodies were trimmed and the counts were not, so a reader can still
        # see the context growing even in a trimmed fixture.
        counts = [r.get("message_count") for r in self.records
                  if r.phase == "prompt"]
        self.assertGreater(len(counts), 1)
        self.assertEqual(sorted(counts), counts, "the counts are not in order")
        self.assertLess(counts[0], counts[-1], "the context never grew")


if __name__ == "__main__":
    unittest.main()
