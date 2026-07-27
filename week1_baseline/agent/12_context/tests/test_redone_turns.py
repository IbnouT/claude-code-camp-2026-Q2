"""A redone turn keeps its number, so the log has to say the number was reused.

`/retry` and `/undo` step the turn counter back, which is what a person means by redoing
turn three, so `n` is deliberately NOT unique. That left the log ambiguous: one real
session carries four turns all labelled 3, and a reader addressing turns by that number
reached the first and silently hid the other three.

Asserted against the written file, because the file is what any reader consumes.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from boukensha.logger import Logger


def _read(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


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
