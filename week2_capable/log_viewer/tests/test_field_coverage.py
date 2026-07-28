"""Every field the log carries is SURFACED somewhere, not merely present.

Ibnou's rule: "we should be able to view the data in different angles... What we want to
prevent is having the data and not be able to see what we are looking into it if that
info is present."

The raw lens prints whole records, so technically nothing is invisible. That is not the
same as surfaced. A reader chasing why a turn died on `max_tokens` should not have to
find the ceiling by reading JSON, and a field that only ever appears as raw JSON has all
the discoverability of not being logged at all.

So this converts the rule from an intention into something that fails a run: for every
field the fixtures carry, some renderer must NAME it. A field the writer gains with no
home in the viewer fails here on the next run rather than going unseen for a month.

RAW_ONLY is the escape hatch and it works like the import allowlist: a field goes in it
with a reason, which makes leaving something raw a decision somebody makes visibly rather
than an omission nobody notices.
"""

import json
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
SOURCE = HERE.parent / "logviewer"

#: Fields carried on every record, which the shell handles rather than any one lens.
UNIVERSAL = {"phase", "at", "session_id"}

#: Fields deliberately left to the raw lens, each with the reason it earns that. Adding
#: a name here is a decision, the way adding an import to the boundary allowlist is.
RAW_ONLY: dict[tuple[str, str], str] = {
    ("session_start", "schema"):
        "the log format version, which matters to a reader of the FILE rather than to "
        "a reader of the session. It is checked by the reader, not shown to a person.",
    ("compaction", "context_window"):
        "the same window the response records carry, and the window panel reads it "
        "there. Two copies of one number in one view invites them disagreeing.",
    ("prompt", "context_window"):
        "as above, the window is reported once from the response records.",
}


def _fields_in_fixtures() -> dict[str, set[str]]:
    """Every field name each phase carries, across every fixture."""
    seen: dict[str, set[str]] = {}
    for path in sorted(FIXTURES.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            phase = record.get("phase")
            if not phase:
                continue
            seen.setdefault(phase, set()).update(
                key for key in record if key not in UNIVERSAL)
    return seen


def _renderer_source() -> str:
    """Every module that decides what a page says.

    `logview` and `sessions` are excluded on purpose: reading a field is not surfacing
    it, and a check that counted the reader would pass on a field the reader parses and
    no page ever prints.
    """
    parts = []
    for name in ("insights.py", "logweb.py", "html.py"):
        parts.append((SOURCE / name).read_text(encoding="utf-8"))
    return "\n".join(parts)


class TestNothingInTheLogIsUnsurfaced(unittest.TestCase):
    def setUp(self):
        self.fields = _fields_in_fixtures()
        self.source = _renderer_source()

    def test_the_fixtures_carry_enough_to_check(self):
        # A coverage test over an empty field set passes and means nothing.
        self.assertGreaterEqual(len(self.fields), 12,
                                f"only {len(self.fields)} phases in the fixtures")
        total = sum(len(v) for v in self.fields.values())
        # A floor rather than the exact count, so a fixture gaining a field does not
        # fail this, and an empty or truncated fixture does.
        self.assertGreaterEqual(total, 60, f"only {total} field slots to check")

    def test_every_field_is_named_by_a_renderer(self):
        missing = []
        for phase, names in sorted(self.fields.items()):
            for name in sorted(names):
                if (phase, name) in RAW_ONLY:
                    continue
                # Named as a log key, `"cost_usd"`, or through the object the reader
                # already built from it, `summary.provider`. Both are surfacing. The
                # match is anchored so `n` cannot match `name` and `max` cannot match
                # `max_tokens`.
                pattern = (rf'["\']{re.escape(name)}["\']'
                           rf'|\.{re.escape(name)}\b')
                if not re.search(pattern, self.source):
                    missing.append(f"{phase}.{name}")
        self.assertEqual([], missing,
                         "these fields are in the log and named by no renderer, so a "
                         f"reader can only find them as raw JSON: {missing}")

    def test_the_raw_only_list_is_reasoned_and_not_a_dumping_ground(self):
        for key, reason in RAW_ONLY.items():
            with self.subTest(field=".".join(key)):
                self.assertGreater(len(reason), 40,
                                   "a field is left raw with a reason, not a shrug")

    def test_the_raw_only_list_only_names_fields_that_exist(self):
        # A stale exemption silently excuses nothing and hides that it is stale.
        for phase, name in RAW_ONLY:
            with self.subTest(field=f"{phase}.{name}"):
                self.assertIn(phase, self.fields, f"{phase} is not in any fixture")
                self.assertIn(name, self.fields[phase],
                              f"{phase}.{name} is exempted and not in any fixture")


if __name__ == "__main__":
    unittest.main()
