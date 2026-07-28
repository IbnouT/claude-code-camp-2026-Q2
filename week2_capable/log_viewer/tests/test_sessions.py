"""Finding a session and describing it well enough to choose one.

Discovery must survive a directory that is empty, a file that is half written, and a
log with no snapshot, because all three are ordinary states rather than errors.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from logviewer.sessions import list_sessions, resolve, summarize


def make_dir():
    return Path(tempfile.mkdtemp(prefix="sessions-"))


def write_session(directory, name, lines, mtime=None):
    path = directory / f"{name}.jsonl"
    path.write_text("".join(json.dumps(l) + "\n" for l in lines))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


COMPLETE = [
    {"phase": "session_start", "provider": "anthropic", "model": "claude-haiku-4-5",
     "task": "player"},
    {"phase": "turn", "n": 1},
    {"phase": "iteration", "n": 1},
    {"phase": "tool_call", "name": "look", "id": "a", "args": {}},
    {"phase": "tool_result", "name": "look", "tool_use_id": "a", "ok": True,
     "result": "a room"},
    {"phase": "response", "input_tokens": 1000, "output_tokens": 20,
     "cost_usd": 0.01},
    {"phase": "turn_end", "reason": "completed", "iterations": 1, "tokens": 1020},
]


class TestDiscovery(unittest.TestCase):
    def test_sessions_are_newest_first(self):
        directory = make_dir()
        now = time.time()
        write_session(directory, "older", COMPLETE, mtime=now - 600)
        write_session(directory, "newer", COMPLETE, mtime=now)
        self.assertEqual(["newer", "older"],
                         [s.id for s in list_sessions(directory)])

    def test_an_empty_directory_is_an_empty_list(self):
        # Having written no sessions yet is ordinary, not an error.
        self.assertEqual([], list_sessions(make_dir()))

    def test_a_missing_directory_is_an_empty_list(self):
        self.assertEqual([], list_sessions(make_dir() / "nope"))

    def test_non_jsonl_files_are_ignored(self):
        directory = make_dir()
        (directory / "notes.txt").write_text("hello")
        write_session(directory, "real", COMPLETE)
        self.assertEqual(["real"], [s.id for s in list_sessions(directory)])


class TestSummaries(unittest.TestCase):
    def test_a_complete_session_reports_its_facts(self):
        directory = make_dir()
        path = write_session(directory, "20260726T010101Z-abc123", COMPLETE)
        summary = summarize(path)
        self.assertEqual("anthropic", summary.provider)
        self.assertEqual("claude-haiku-4-5", summary.model)
        self.assertEqual("player", summary.task)
        self.assertEqual(1, summary.turns)
        self.assertEqual(1, summary.tool_calls)
        self.assertEqual("completed", summary.outcome)
        self.assertEqual("$0.0100", summary.render_cost())

    def test_the_timestamp_comes_from_the_filename(self):
        directory = make_dir()
        path = write_session(directory, "20260726T010101Z-abc123", COMPLETE)
        summary = summarize(path)
        self.assertIsNotNone(summary.started_at)
        self.assertEqual("2026-07-26 01:01", summary.when)

    def test_a_session_with_no_snapshot_still_summarizes(self):
        # A partially written session is a normal thing to want to look at.
        directory = make_dir()
        path = write_session(directory, "nosnapshot", [
            {"phase": "turn", "n": 1},
            {"phase": "response", "input_tokens": 5, "output_tokens": 1},
        ])
        summary = summarize(path)
        self.assertIsNone(summary.provider)
        self.assertEqual(1, summary.turns)

    def test_a_turn_that_never_ended_reads_as_in_progress(self):
        directory = make_dir()
        path = write_session(directory, "running", [
            {"phase": "session_start", "model": "m"},
            {"phase": "turn", "n": 1},
            {"phase": "iteration", "n": 1},
        ])
        self.assertEqual("in progress", summarize(path).outcome)

    def test_a_session_with_no_turns_says_so(self):
        directory = make_dir()
        path = write_session(directory, "empty", [{"phase": "session_start"}])
        self.assertEqual("no turns", summarize(path).outcome)

    def test_an_unpriced_session_reports_unavailable_not_zero(self):
        # Reporting $0.00 would claim the run was free.
        directory = make_dir()
        path = write_session(directory, "unpriced", [
            {"phase": "turn", "n": 1},
            {"phase": "response", "input_tokens": 10, "output_tokens": 1},
            {"phase": "turn_end", "reason": "completed", "iterations": 1},
        ])
        summary = summarize(path)
        self.assertIsNone(summary.cost)
        self.assertEqual("unavailable", summary.render_cost())

    def test_failures_are_counted(self):
        directory = make_dir()
        path = write_session(directory, "failing", COMPLETE + [
            {"phase": "tool_result", "name": "look", "tool_use_id": "b",
             "ok": False, "result": "boom"},
            {"phase": "retry", "attempt": 1},
        ])
        self.assertEqual(2, summarize(path).failures)


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.dir = make_dir()
        now = time.time()
        write_session(self.dir, "20260726T010101Z-aaa111", COMPLETE, mtime=now - 60)
        write_session(self.dir, "20260726T020202Z-bbb222", COMPLETE, mtime=now)

    def test_latest_names_the_most_recent(self):
        # What someone asks for after a run that surprised them.
        self.assertEqual("20260726T020202Z-bbb222",
                         resolve("latest", self.dir).id)

    def test_a_full_id_resolves(self):
        self.assertEqual("20260726T010101Z-aaa111",
                         resolve("20260726T010101Z-aaa111", self.dir).id)

    def test_a_filename_resolves(self):
        self.assertEqual("20260726T010101Z-aaa111",
                         resolve("20260726T010101Z-aaa111.jsonl", self.dir).id)

    def test_an_unambiguous_prefix_resolves(self):
        # These ids are long and nobody types them in full.
        self.assertEqual("20260726T010101Z-aaa111",
                         resolve("20260726T0101", self.dir).id)

    def test_an_ambiguous_prefix_resolves_to_nothing(self):
        self.assertIsNone(resolve("20260726T0", self.dir))

    def test_an_unknown_id_resolves_to_nothing(self):
        self.assertIsNone(resolve("nope", self.dir))

    def test_resolving_in_an_empty_directory_is_none(self):
        self.assertIsNone(resolve("latest", make_dir()))
