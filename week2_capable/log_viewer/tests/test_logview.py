"""Reading a session log: records, tolerance at the edges, turns, pairing, totals.

The logger is the only writer and the file is the interface, so these tests write
fixture logs and read them back. Nothing here needs an agent, a backend or a network,
which is the point of the reader being a reader.
"""

import json
import tempfile
import unittest
from pathlib import Path

from logviewer.logview import (
    KNOWN_PHASES, Record, cost_breakdown, group_turns, pair_tools, parse_line,
    read, totals,
)


def write_log(lines, name="s.jsonl", trailing_newline=True):
    """A fixture log on disk. ``trailing_newline`` false simulates a live write."""
    path = Path(tempfile.mkdtemp()) / name
    body = "".join(json.dumps(l) + "\n" for l in lines)
    if not trailing_newline and body:
        body = body[:-1]
    path.write_text(body)
    return path


class TestParsing(unittest.TestCase):
    def test_every_known_phase_reads(self):
        for phase in KNOWN_PHASES:
            with self.subTest(phase=phase):
                record = parse_line(json.dumps({"phase": phase}), 1)
                self.assertEqual(phase, record.phase)
                self.assertTrue(record.known)

    def test_an_unknown_phase_still_reads(self):
        # A log written by a newer step must stay readable, so the vocabulary is
        # never asserted closed.
        record = parse_line(json.dumps({"phase": "something_new", "x": 1}), 1)
        self.assertEqual("something_new", record.phase)
        self.assertFalse(record.known)
        self.assertEqual(1, record.get("x"))

    def test_a_malformed_line_is_reported_with_its_position(self):
        record = parse_line("{not json", 7)
        self.assertTrue(record.malformed)
        self.assertEqual(7, record.line)

    def test_a_json_value_that_is_not_an_object_is_malformed(self):
        self.assertTrue(parse_line("[1,2,3]", 2).malformed)

    def test_blank_lines_are_nothing(self):
        self.assertIsNone(parse_line("   ", 1))


class TestToleranceAtTheEdges(unittest.TestCase):
    def test_a_half_written_final_line_reads_as_in_progress(self):
        # The normal state of a live session: the writer is mid-append. That is not
        # corruption and must not be reported as a malformed record.
        path = write_log([{"phase": "turn", "n": 1}], trailing_newline=False)
        path.write_text(path.read_text() + '\n{"phase": "iter')
        result = read(path)
        self.assertTrue(result.incomplete)
        self.assertEqual(0, result.malformed)
        self.assertEqual(["turn"], [r.phase for r in result.records])

    def test_following_completes_the_line_without_duplicating_it(self):
        path = write_log([{"phase": "turn", "n": 1}])
        first = read(path)
        with path.open("a") as handle:
            handle.write('{"phase": "iteration", "n": 1}')   # no newline yet
        second = read(path, first.offset)
        self.assertEqual([], [r.phase for r in second.records])
        self.assertTrue(second.incomplete)
        with path.open("a") as handle:
            handle.write("\n")                                # now complete
        third = read(path, second.offset)
        self.assertEqual(["iteration"], [r.phase for r in third.records])

    def test_a_missing_file_is_empty_not_an_error(self):
        result = read(Path(tempfile.mkdtemp()) / "absent.jsonl")
        self.assertEqual([], result.records)

    def test_line_numbers_survive_a_resumed_read(self):
        path = write_log([{"phase": "turn", "n": 1}, {"phase": "iteration", "n": 1}])
        first = read(path)
        with path.open("a") as handle:
            handle.write("{bad\n")
        second = read(path, first.offset)
        self.assertEqual(3, second.records[0].line)


class TestTroubleIsNeverQuiet(unittest.TestCase):
    def test_failures_and_warnings_are_flagged(self):
        for line, expected in [
            ({"phase": "retry", "attempt": 1}, True),
            ({"phase": "limit_reached", "kind": "max_tokens"}, True),
            ({"phase": "log_error"}, True),
            ({"phase": "tool_result", "ok": False}, True),
            ({"phase": "tool_result", "ok": True}, False),
            ({"phase": "response"}, False),
        ]:
            with self.subTest(phase=line["phase"], ok=line.get("ok")):
                self.assertEqual(expected, parse_line(json.dumps(line), 1).trouble)


class TestTurns(unittest.TestCase):
    def _session(self):
        return write_log([
            {"phase": "session_start", "model": "m", "provider": "p"},
            {"phase": "turn", "n": 1},
            {"phase": "iteration", "n": 1},
            {"phase": "tool_call", "name": "look", "id": "a", "args": {}},
            {"phase": "tool_result", "name": "look", "tool_use_id": "a",
             "result": "a room", "ok": True},
            {"phase": "response", "input_tokens": 100, "output_tokens": 10,
             "cost_usd": 0.001, "task": "player", "provider": "p", "model": "m"},
            {"phase": "turn_end", "reason": "completed", "iterations": 1,
             "tokens": 110},
            {"phase": "turn", "n": 2},
            {"phase": "iteration", "n": 1},
            {"phase": "response", "input_tokens": 900, "output_tokens": 20,
             "cost_usd": 0.02, "task": "player", "provider": "p", "model": "m"},
            {"phase": "limit_reached", "kind": "max_tokens", "n": 920, "max": 900},
            {"phase": "turn_end", "reason": "max_tokens", "iterations": 1,
             "tokens": 920},
        ])

    def test_records_group_into_turns_in_order(self):
        records = read(self._session()).records
        turns = group_turns(records)
        self.assertEqual([1, 2], [t.number for t in turns])
        self.assertEqual("completed", turns[0].reason)
        self.assertEqual("max_tokens", turns[1].reason)

    def test_a_tripped_turn_says_so(self):
        turns = group_turns(read(self._session()).records)
        self.assertFalse(turns[0].tripped)
        self.assertTrue(turns[1].tripped)

    def test_records_before_the_first_turn_belong_to_no_turn(self):
        # The session snapshot is not part of a turn and must not be attributed to
        # one, or turn 1 inherits it.
        turns = group_turns(read(self._session()).records)
        self.assertNotIn("session_start", [r.phase for r in turns[0].records])

    def test_a_call_is_paired_with_its_result_by_id(self):
        records = read(self._session()).records
        pairs = pair_tools(records)
        self.assertEqual(1, len(pairs))
        call, result = pairs[0]
        self.assertEqual("look", call.get("name"))
        self.assertEqual("a room", result.get("result"))

    def test_an_unpaired_call_is_kept_not_dropped(self):
        # A call whose result never arrived is usually the thing being investigated.
        path = write_log([{"phase": "tool_call", "name": "look", "id": "z",
                           "args": {}}])
        pairs = pair_tools(read(path).records)
        self.assertEqual(1, len(pairs))
        self.assertIsNone(pairs[0][1])


class TestTotalsQuoteTheWriter(unittest.TestCase):
    def _session(self):
        return write_log([
            {"phase": "session_start"},
            {"phase": "turn", "n": 1},
            {"phase": "iteration", "n": 1},
            {"phase": "response", "input_tokens": 100, "output_tokens": 10,
             "cost_usd": 0.001},
            {"phase": "response", "input_tokens": 5000, "output_tokens": 20,
             "cost_usd": 0.05},
            {"phase": "turn_end", "reason": "completed", "iterations": 2},
        ])

    def test_cost_is_summed_from_what_was_logged(self):
        figures = totals(read(self._session()).records)
        self.assertAlmostEqual(0.051, figures["cost"])

    def test_peak_input_is_the_largest_single_prompt(self):
        # Not the sum: the largest prompt is the window question, the sum is spend.
        figures = totals(read(self._session()).records)
        self.assertEqual(5000, figures["peak_input_tokens"])
        self.assertEqual(5100, figures["input_tokens"])

    def test_no_logged_cost_reports_none_rather_than_zero(self):
        path = write_log([
            {"phase": "turn", "n": 1},
            {"phase": "response", "input_tokens": 10, "output_tokens": 1},
            {"phase": "turn_end", "reason": "completed", "iterations": 1},
        ])
        self.assertIsNone(totals(read(path).records)["cost"])

    def test_a_partial_cost_is_flagged_as_partial(self):
        path = write_log([
            {"phase": "turn", "n": 1},
            {"phase": "response", "input_tokens": 10, "cost_usd": 0.001},
            {"phase": "response", "input_tokens": 10},
            {"phase": "turn_end", "reason": "completed", "iterations": 2},
        ])
        figures = totals(read(path).records)
        self.assertTrue(figures["cost_partial"])

    def test_an_empty_session_totals_to_nothing_without_raising(self):
        figures = totals([])
        self.assertEqual(0, figures["turns"])
        self.assertIsNone(figures["cost"])
        self.assertIsNone(figures["largest_turn"])


class TestCostBreakdown(unittest.TestCase):
    def test_cost_groups_by_task_provider_and_model(self):
        path = write_log([
            {"phase": "response", "task": "player", "provider": "anthropic",
             "model": "haiku", "input_tokens": 10, "cost_usd": 0.01},
            {"phase": "response", "task": "player", "provider": "anthropic",
             "model": "haiku", "input_tokens": 20, "cost_usd": 0.02},
            {"phase": "response", "task": "player", "provider": "openai",
             "model": "gpt", "input_tokens": 5, "cost_usd": 0.005},
        ])
        rows = cost_breakdown(read(path).records)
        self.assertEqual(2, len(rows))
        self.assertEqual(2, rows[0]["calls"])
        self.assertAlmostEqual(0.03, rows[0]["cost"])

    def test_a_group_missing_a_cost_is_marked_not_known(self):
        path = write_log([
            {"phase": "response", "model": "m", "cost_usd": 0.01},
            {"phase": "response", "model": "m"},
        ])
        self.assertFalse(cost_breakdown(read(path).records)[0]["cost_known"])


class TestTurnFiguresAreReadNotRecomputed(unittest.TestCase):
    """A turn's totals come from its own `turn_end`, never from re-summing.

    The writer added them up where the model, the usage and the rates were all in
    hand. A reader adding them up again would eventually disagree with the bill,
    and amplification it could not produce at all: the count of distinct things
    sent exists only in the agent, not in the message stream.
    """

    LOG = [
        {"phase": "turn", "n": 1},
        {"phase": "response", "text": "hi", "input_tokens": 100,
         "output_tokens": 10, "cost_usd": 0.001},
        {"phase": "turn_end", "reason": "max_tokens", "iterations": 3,
         "tokens": 2260, "input_tokens": 2200, "output_tokens": 60,
         "cost_usd": 0.0481, "duration_ms": 1234,
         "usage": {"fresh_input": 200, "cache_read": 1900, "cache_write": 100,
                   "output": 60},
         "unique_tokens": 16110, "amplification": 133.7},
    ]

    def _turn(self):
        records = [Record(phase=r["phase"], data=r, line=i)
                   for i, r in enumerate(self.LOG, 1)]
        return group_turns(records)[0]

    def test_the_logged_totals_are_carried_through(self):
        turn = self._turn()
        self.assertEqual(2260, turn.tokens)
        self.assertEqual(2200, turn.input_tokens)
        self.assertEqual(60, turn.output_tokens)
        self.assertEqual(1234, turn.duration_ms)
        # NOT the 0.001 of the single response: the turn's own figure wins.
        self.assertEqual(0.0481, turn.cost)

    def test_the_four_classes_and_amplification_are_carried_through(self):
        turn = self._turn()
        self.assertEqual(2200, sum(v for k, v in turn.usage.items()
                                   if k != "output"))
        self.assertEqual(133.7, turn.amplification)
        self.assertEqual(16110, turn.unique_tokens)

    def test_a_turn_with_no_cost_says_unavailable_not_zero(self):
        records = [Record(phase="turn", data={"n": 1}, line=1),
                   Record(phase="turn_end",
                          data={"reason": "completed", "iterations": 1}, line=2)]
        turn = group_turns(records)[0]
        self.assertIsNone(turn.cost)
        self.assertEqual("unavailable", turn.render_cost())

    def test_a_log_written_before_these_fields_existed_still_groups(self):
        # Sessions on disk predate every one of them. A reader that required
        # them would refuse to open its own project's history.
        records = [Record(phase="turn", data={"n": 1}, line=1),
                   Record(phase="turn_end",
                          data={"reason": "completed", "iterations": 2,
                                "tokens": 500}, line=2)]
        turn = group_turns(records)[0]
        self.assertEqual(500, turn.tokens)
        self.assertIsNone(turn.amplification)
        self.assertIsNone(turn.usage)
