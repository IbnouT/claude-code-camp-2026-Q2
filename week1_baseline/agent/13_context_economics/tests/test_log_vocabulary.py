"""Every phase the logger can emit, asserted against the FILE.

The file is the interface every reader consumes, so a field asserted only through
`RecordingLogger` is untested from a reader's point of view: that fake captures what
the agent PASSED and never runs the real `Logger`. It is how three field losses stayed
green in one session, the agent having computed them and nobody having checked they
arrived.

So this drives the real writer for every phase in its own vocabulary and reads the
records straight back off disk. A field the writer drops fails here rather than in a
session somebody notices weeks later.

The reader's half of the same contract lives with the log viewer, which is a separate
program and tests against a checked-in fixture rather than importing this package. The
logger's refusal to raise while describing something has its own file,
`test_logger_robustness.py`.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from boukensha.logger import Logger
from boukensha.message import Message

from .helper import StubTransport, build_agent, end_turn, ok

#: The field each phase must carry into the file, keyed by phase. This is the same
#: table the log viewer's plan audits, so the plan and the writer cannot drift
#: without one of them failing.
REQUIRED = {
    "session_start": ("schema",),
    "turn": ("n",),
    "iteration": ("n", "max"),
    "prompt": ("messages", "tools", "message_count", "tool_count",
               "context_window"),
    "response": ("text", "usage", "stop_reason", "duration_ms"),
    "tool_call": ("name", "args", "id"),
    "tool_result": ("name", "result", "ok", "tool_use_id"),
    "reasoning": ("text", "redacted"),
    "plan": ("text",),
    "compaction": ("before", "dropped", "compressed", "summarized",
                   "over_budget", "context_window"),
    "retry": ("attempt", "wait", "status"),
    "limit_reached": ("kind", "n", "max"),
    "turn_end": ("reason", "iterations", "tokens", "input_tokens",
                 "output_tokens", "cost_usd", "duration_ms", "usage",
                 "unique_tokens", "amplification"),
    "raw": ("data",),
}

#: Emitted only when the writer itself fails, so it is exercised separately.
BY_FAILURE_ONLY = ("log_error",)


def _read(path: Path) -> list[dict]:
    """Records straight off disk, with no reader in between.

    Deliberately not the log viewer's reader. That is a different program with its
    own tests, and borrowing it here would mean a bug in it could hide a bug in
    this writer.
    """
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _write_everything(path: Path) -> Logger:
    """One call to every writer method, with a value for every field."""
    logger = Logger(session_id="vocab", log=path, debug=True,
                    snapshot={"model": "m", "provider": "p", "task": "t",
                              "system": "you are a player",
                              "context_window": 200_000})
    logger.turn(n=1)
    logger.iteration(n=1, max=25)
    logger.prompt(messages=[Message.user("hello")], tools={"look": object()},
                  context_window=200_000)
    logger.reasoning(text="thinking", redacted=False)
    logger.plan(text="I will look around")
    logger.tool_call(name="look", args={"target": "room"}, id="toolu_1")
    logger.tool_result(name="look", result="a room", ok=True,
                       tool_use_id="toolu_1")
    logger.response(text="I see a room",
                    usage={"input_tokens": 100, "output_tokens": 10},
                    stop_reason="end_turn", duration_ms=12.5)
    logger.compaction(before=180_000, dropped=4, context_window=200_000,
                      compressed=2, summarized=True, over_budget=False)
    logger.retry(attempt=1, wait=0.5, status=529)
    logger.limit_reached(kind="max_iterations", n=25, max=25)
    logger.raw(data={"anything": True})
    logger.turn_end(reason="max_iterations", iterations=25, tokens=2260,
                    input_tokens=2200, output_tokens=60, cost_usd=0.0481,
                    duration_ms=1234,
                    usage={"fresh_input": 200, "cache_read": 1900,
                           "cache_write": 100, "output": 60},
                    unique_tokens=16110, amplification=133.7)
    logger.close()
    return logger


class TestEveryPhaseReachesTheFile(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "vocab.jsonl"
        _write_everything(self.path)
        self.records = _read(self.path)
        self.by_phase = {}
        for record in self.records:
            self.by_phase.setdefault(record.get("phase"), []).append(record)

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_line_is_one_complete_json_object(self):
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"), "the last line was left half written")
        self.assertEqual(len([l for l in text.splitlines() if l.strip()]),
                         len(self.records))

    def test_every_phase_in_the_vocabulary_was_written(self):
        expected = set(Logger.PHASES) - set(BY_FAILURE_ONLY)
        missing = sorted(expected - set(self.by_phase))
        self.assertEqual([], missing, f"phases never reached the file: {missing}")

    def test_every_required_field_arrived(self):
        problems = []
        for phase, fields in REQUIRED.items():
            records = self.by_phase.get(phase)
            if not records:
                problems.append(f"{phase}: no record at all")
                continue
            data = records[-1]
            for field in fields:
                if field not in data:
                    problems.append(f"{phase}.{field}")
        self.assertEqual([], problems, f"fields missing from the file: {problems}")

    def test_every_record_carries_its_identity_and_its_time(self):
        # `at` and `session_id` are on every event and were surfaced nowhere in
        # any design until the audit found them.
        for record in self.records:
            phase = record.get("phase")
            self.assertIn("at", record, f"{phase} has no timestamp")
            self.assertIn("session_id", record, f"{phase} has no session id")

    def test_the_prompt_payload_is_the_whole_message_not_a_count(self):
        # This is what makes the context diff possible, so it is asserted rather
        # than assumed.
        data = self.by_phase["prompt"][-1]
        self.assertEqual(1, data["message_count"])
        self.assertEqual(1, len(data["messages"]))
        self.assertIn("hello", str(data["messages"][0]))

    def test_a_debug_only_phase_is_absent_when_debug_is_off(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "quiet.jsonl"
            logger = Logger(session_id="quiet", log=path)
            logger.raw(data={"secret": True})
            logger.close()
            phases = {r.get("phase") for r in _read(path)}
            self.assertNotIn("raw", phases)

class TestSessionStartRecordsWhatAReaderCannotDerive(unittest.TestCase):
    """The rates, because no reader can get them from the message stream.

    A log viewer asking "what would this session have cost without caching" needs the
    per-class rates. They are a fact about the model, not about the run, so the only
    honest options are that the writer records them or that the reader abstains. The
    third option, a reader owning its own price table, is a second cost calculation,
    and a second cost calculation eventually disagrees with the bill.

    Same reasoning as `unique_tokens` on `turn_end`: derive or log, never reconstruct.
    """

    def _start(self, **kwargs):
        agent, assembled = build_agent(
            StubTransport(ok(end_turn("done"))), "rates_recorded", **kwargs)
        agent.run()
        assembled.logger.close()
        starts = [r for r in _read(assembled.logger.path)
                  if r.get("phase") == "session_start"]
        self.assertTrue(starts, "no session_start reached the file")
        return starts[-1]

    def test_the_rates_reach_the_file(self):
        start = self._start()
        self.assertIn("rates", start)
        rates = start["rates"]
        # A priced model records a table with at least an input rate. An unpriced one
        # records None, which is not a zero.
        if rates is not None:
            self.assertIn("input", rates)
            self.assertIsNotNone(rates["input"])

    def test_the_caching_capability_is_recorded_beside_them(self):
        # A reader explaining why a session cached nothing needs the minimum, which
        # is a per-model fact spanning an eightfold range on one provider alone.
        start = self._start()
        self.assertIn("caches", start)
        self.assertIn("cache_min_tokens", start)
        self.assertIsInstance(start["caches"], bool)
        self.assertIsInstance(start["cache_min_tokens"], int)

    def test_the_rates_are_the_backend_s_own_and_not_a_copy(self):
        agent, assembled = build_agent(
            StubTransport(ok(end_turn("done"))), "rates_match")
        agent.run()
        assembled.logger.close()
        start = [r for r in _read(assembled.logger.path)
                 if r.get("phase") == "session_start"][-1]
        self.assertEqual(assembled.builder.backend.rates, start["rates"])


class TestARedoneTurnIsRecordedAsARepeat(unittest.TestCase):
    """`n` is the user-facing turn number and is deliberately NOT unique.

    `/retry` and `/undo` step the counter back, so a redone turn keeps the number it
    had, which is what a person means by redoing turn three. That is right, and it left
    the log ambiguous: one real session carries four turns all labelled 3, and a reader
    addressing turns by that number reached the first and silently hid the other three,
    along with both compaction records in the whole corpus.

    So the writer says when a number is being reused. It does not renumber, because the
    number is not the writer's to change.
    """

    def _turns(self, numbers):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            logger = Logger(session_id="s", log=path)
            for n in numbers:
                logger.turn(n=n)
            logger.close()
            return [r for r in _read(path) if r.get("phase") == "turn"]

    def test_a_first_attempt_carries_no_attempt_field(self):
        # Absence, not 1, because that is how every other optional field here reads.
        for record in self._turns([1, 2, 3]):
            self.assertNotIn("attempt", record)

    def test_a_reused_number_is_counted(self):
        records = self._turns([1, 2, 3, 3, 3])
        self.assertEqual([None, None, None, 2, 3],
                         [r.get("attempt") for r in records])

    def test_the_number_itself_is_never_rewritten(self):
        # Renumbering would be the writer lying to make a reader's job easier.
        records = self._turns([1, 2, 3, 3, 3])
        self.assertEqual([1, 2, 3, 3, 3], [r["n"] for r in records])

    def test_counting_is_per_number_rather_than_a_running_total(self):
        records = self._turns([1, 1, 2, 1])
        self.assertEqual([None, 2, None, 3], [r.get("attempt") for r in records])


if __name__ == "__main__":
    unittest.main()
