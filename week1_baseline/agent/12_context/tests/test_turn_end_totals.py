"""What `turn_end` records, and why a summed total is not enough.

Steps 10 and 11 logged the turn's input/output split and its cost. This step's
rewrite replaced all three with one summed `tokens`, and nothing noticed because a
plausible number was still there. It is the same failure shape as the wind-down
losing its duration: a field stops being written and the suite stays green because
no test ever asserted the field existed.

A sum cannot be taken apart again, so both forms are recorded and both are asserted.
"""

import json
import tempfile
import unittest
from pathlib import Path

from boukensha.logger import Logger

from .helper import (
    RecordingLogger, StubTransport, add_ping_tool, build_agent, end_turn, ok,
    tool_use,
)


def _turn_ends(path):
    """Every turn_end in a written log, parsed from the file itself."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if record.get("phase") == "turn_end":
            out.append(record)
    return out


def _written(**kwargs):
    """Drive the REAL logger and read the record back off disk.

    RecordingLogger captures the kwargs the agent passes, which answers whether
    the agent computed a field. It cannot answer whether the field reached the
    file, and the file is the interface every reader consumes. The two questions
    look identical until the logger drops something on the way through, so
    anything about the RECORD is asserted against the record.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "s.jsonl"
        logger = Logger(session_id="s", log=path)
        logger.turn_end(**kwargs)
        logger.close()
        records = _turn_ends(path)
        assert records, "the logger wrote no turn_end at all"
        return records[-1]


def _end(log):
    ends = log.kinds("turn_end")
    assert ends, "no turn_end was logged at all"
    return ends[-1]


class TestTurnEndCarriesTheTurnsTotals(unittest.TestCase):
    def test_the_split_survives_beside_the_sum(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping", itok=1200, otok=20)),
                          ok(end_turn("done", itok=1000, otok=40))),
            "totals_split", setup=add_ping_tool, logger=log)
        agent.run()
        end = _end(log)
        self.assertEqual(2260, end["tokens"])
        self.assertEqual(2200, end["input_tokens"])
        self.assertEqual(60, end["output_tokens"])
        # The sum and the split describe the same calls, so they must agree.
        self.assertEqual(end["tokens"],
                         end["input_tokens"] + end["output_tokens"])

    def test_an_unpriced_turn_reports_no_cost_rather_than_zero(self):
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(end_turn("done", itok=1000, otok=40))),
            "totals_cost", logger=log)
        agent.run()
        end = _end(log)
        # Either a real figure or the key absent. A zero would read as free.
        self.assertNotEqual(0, end.get("cost_usd", None))

    def test_a_turn_stopped_by_a_ceiling_reports_the_same_totals(self):
        # The wind-down builds its own turn_end, so it has to go through the same
        # helper. It did not for duration, and that shipped.
        log = RecordingLogger()
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping", itok=6000, otok=20)),
                          ok(end_turn("wound down", itok=800, otok=30))),
            "totals_ceiling", setup=add_ping_tool, logger=log,
            max_iterations=1)
        agent.run()
        end = _end(log)
        self.assertNotEqual("completed", end["reason"])
        for field in ("tokens", "input_tokens", "output_tokens", "duration_ms"):
            self.assertIn(field, end, f"{field} missing on a stopped turn")

    def test_an_absent_total_is_an_absent_key_not_a_null(self):
        """Absence is the key missing, never a null sitting in the record.

        `tokens` was written unconditionally while every other optional total was
        guarded, so it appeared in EVERY turn_end while carrying a value in only
        some. A reader counting the field's presence would conclude it was always
        recorded, and a reader reading its value would find nothing. Absence has
        to look like absence in the file, not just in the value.
        """
        end = _written(reason="completed", iterations=1)
        for field in ("tokens", "input_tokens", "output_tokens", "cost_usd",
                      "duration_ms"):
            self.assertNotIn(field, end,
                             f"{field} present as a null rather than absent")


class TestTheFieldsReachTheFile(unittest.TestCase):
    """The end-to-end question: does a real run leave them in the log?

    Every other test here asserts what the agent COMPUTED. This one asserts what
    a reader will find, which is the only thing the viewer can consume. Three
    field losses this session were invisible at the kwargs layer and visible in
    the file, so the file gets its own test.
    """

    def _run_and_read(self, name, **kwargs):
        agent, _ = build_agent(
            StubTransport(ok(tool_use("ping")), ok(end_turn("done"))),
            name, setup=add_ping_tool, **kwargs)
        agent.run()
        agent._logger.close()
        records = _turn_ends(agent._logger.path)
        self.assertTrue(records, "no turn_end reached the file")
        return records[-1]

    def test_a_completed_turn_writes_every_total(self):
        end = self._run_and_read("e2e_completed")
        for field in ("tokens", "input_tokens", "output_tokens", "duration_ms"):
            self.assertIn(field, end, f"{field} never reached the file")
        self.assertEqual(end["tokens"],
                         end["input_tokens"] + end["output_tokens"])

    def test_a_turn_stopped_by_a_ceiling_writes_them_too(self):
        end = self._run_and_read("e2e_stopped", max_iterations=1)
        self.assertNotEqual("completed", end["reason"])
        for field in ("tokens", "input_tokens", "output_tokens",
                      "duration_ms"):
            self.assertIn(field, end, f"{field} missing from a stopped turn")


if __name__ == "__main__":
    unittest.main()
