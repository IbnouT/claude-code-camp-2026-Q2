"""Logging must never break the thing it is describing.

`tool_result` coerced its payload with `str(result)` BEFORE the guarded write, so a
value whose own `__str__` raises propagated out of the logger and killed the turn.
MCP tools return whatever their server sends, so the payload is not the logger's to
trust, and coercion at the boundary of a `try` is not protection.

Asserted against the written file rather than against what the caller passed, because
the file is what any reader consumes.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from boukensha.logger import Logger


class Hostile:
    """A payload whose own text conversion fails."""

    def __repr__(self):
        raise RuntimeError("no")


def _records(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


class TestLoggingNeverBreaksTheRun(unittest.TestCase):
    def _log_one(self, call):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "hostile.jsonl"
            logger = Logger(session_id="hostile", log=path)
            call(logger)
            logger.close()
            return _records(path)

    def test_a_payload_that_cannot_be_printed_is_still_recorded(self):
        records = self._log_one(
            lambda log: log.tool_result(name="look", result=Hostile()))
        results = [r for r in records if r.get("phase") == "tool_result"]
        self.assertEqual(1, len(results), "the event vanished entirely")
        # It says what it could not print rather than pretending it was empty.
        self.assertIn("unprintable", results[-1]["result"])
        self.assertIn("Hostile", results[-1]["result"])
        self.assertEqual("look", results[-1]["name"])

    def test_the_same_holds_for_every_text_field_at_the_boundary(self):
        for name, call in (
            ("reasoning", lambda log: log.reasoning(text=Hostile())),
            ("plan", lambda log: log.plan(text=Hostile())),
            ("response", lambda log: log.response(text=Hostile())),
        ):
            with self.subTest(phase=name):
                records = self._log_one(call)
                written = [r for r in records if r.get("phase") == name]
                self.assertEqual(1, len(written), f"{name} vanished")
                self.assertIn("unprintable", written[-1]["text"])

    def test_a_write_that_fails_anyway_is_recorded_as_a_log_error(self):
        # The fallback still exists for whatever the coercion cannot save.
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "err.jsonl"
            logger = Logger(session_id="err", log=path)
            logger._write_error("tool_result", RuntimeError("disk full"))
            logger.close()
            errors = [r for r in _records(path)
                      if r.get("phase") == "log_error"]
            self.assertEqual(1, len(errors))
            self.assertEqual("tool_result", errors[-1]["original_phase"])
            self.assertIn("disk full", errors[-1]["error"])


if __name__ == "__main__":
    unittest.main()
