"""The journal. Ordering, commit-before-publish, and resumable cursors."""

from __future__ import annotations

import multiprocessing
import sqlite3
import time

import pytest

from mud_gateway.journal import Event, Journal, JournalError, SCHEMA_VERSION


def _die_inside_a_transaction(path, ready):
    db = sqlite3.connect(path)
    db.execute("BEGIN IMMEDIATE")
    db.execute(
        "INSERT INTO events "
        "(session, at, monotonic, kind, trace_id, payload) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", time.time(), time.monotonic(), "wire", None, '{"partial": true}'))
    ready.send(True)
    time.sleep(30)


@pytest.fixture
def journal(tmp_path):
    j = Journal(tmp_path / "events.db")
    yield j
    j.close()


class TestOrdering:
    def test_the_sequence_is_assigned_by_the_journal_and_strictly_increases(self, journal):
        # Not by the caller: two writers or one retry would otherwise duplicate a number,
        # and a subscriber cursor built on duplicates silently skips events.
        seqs = [journal.append("s1", "wire", {"n": i}).seq for i in range(5)]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == 5

    def test_sequences_do_not_restart_per_session(self, journal):
        first = journal.append("s1", "wire", {}).seq
        second = journal.append("s2", "wire", {}).seq
        assert second > first

    def test_last_seq_reports_per_session(self, journal):
        journal.append("s1", "wire", {})
        top = journal.append("s1", "wire", {}).seq
        journal.append("s2", "wire", {})
        assert journal.last_seq("s1") == top
        assert journal.last_seq("absent") == 0


class TestTheResumableCursor:
    def test_since_returns_only_what_follows_the_cursor(self, journal):
        events = [journal.append("s1", "wire", {"n": i}) for i in range(5)]
        rest = journal.since("s1", after=events[2].seq)
        assert [e.payload["n"] for e in rest] == [3, 4]

    def test_a_subscriber_that_dropped_can_resume_exactly(self, journal):
        seen: list[Event] = []
        cancel = journal.subscribe(seen.append)
        journal.append("s1", "wire", {"n": 0})
        cancel()                                    # the subscriber drops here
        journal.append("s1", "wire", {"n": 1})
        journal.append("s1", "wire", {"n": 2})
        missed = journal.since("s1", after=seen[-1].seq)
        assert [e.payload["n"] for e in missed] == [1, 2]

    def test_filtering_by_kind_keeps_the_ordering(self, journal):
        journal.append("s1", "wire", {"n": 0})
        journal.append("s1", "observation", {"n": 1})
        journal.append("s1", "wire", {"n": 2})
        assert [e.payload["n"] for e in journal.since("s1", kind="wire")] == [0, 2]


class TestCommitBeforePublish:
    def test_a_subscriber_only_sees_events_that_are_already_readable(self, journal):
        # A subscriber shown an event a crash would erase is showing something that did not
        # happen, so publication has to follow the commit.
        observed: list[int] = []

        def check(event: Event) -> None:
            # At callback time the row must already be queryable.
            observed.append(len(journal.since(event.session, after=event.seq - 1)))

        journal.subscribe(check)
        journal.append("s1", "wire", {})
        assert observed == [1]

    def test_unsubscribing_stops_delivery(self, journal):
        seen = []
        cancel = journal.subscribe(seen.append)
        journal.append("s1", "wire", {})
        cancel()
        journal.append("s1", "wire", {})
        assert len(seen) == 1


class TestIntegrity:
    def test_an_event_without_a_kind_is_refused(self, journal):
        with pytest.raises(JournalError):
            journal.append("s1", "", {})

    def test_the_trace_id_survives_the_round_trip(self, journal):
        journal.append("s1", "command", {"line": "look"}, trace_id="trace-abc")
        assert journal.since("s1")[0].trace_id == "trace-abc"

    def test_a_payload_round_trips_as_a_dict(self, journal):
        journal.append("s1", "observation", {"room": {"title": "The Bakery"}, "n": [1, 2]})
        assert journal.since("s1")[0].payload["room"]["title"] == "The Bakery"


class TestBlobs:
    def test_identical_bodies_are_stored_once(self, journal):
        first = journal.put_blob(b"a long room description")
        second = journal.put_blob(b"a long room description")
        assert first == second
        assert journal.get_blob(first) == b"a long room description"

    def test_an_absent_digest_returns_none_rather_than_raising(self, journal):
        assert journal.get_blob("0" * 32) is None


class TestDurability:
    def test_events_survive_reopening_the_file(self, tmp_path):
        path = tmp_path / "events.db"
        first = Journal(path)
        first.append("s1", "wire", {"n": 1})
        first.close()
        second = Journal(path)
        try:
            assert second.count("s1") == 1
        finally:
            second.close()

    def test_export_writes_one_json_line_per_event(self, journal, tmp_path):
        journal.append("s1", "wire", {"n": 1})
        journal.append("s1", "wire", {"n": 2})
        out = tmp_path / "s1.jsonl"
        assert journal.export_jsonl("s1", out) == 2
        assert len(out.read_text().splitlines()) == 2
        assert '"kind": "wire"' in out.read_text()

    def test_a_killed_writer_leaves_only_the_committed_prefix(self, tmp_path):
        path = tmp_path / "events.db"
        first = Journal(path)
        first.append("s1", "wire", {"committed": True})
        first.close()

        parent, child = multiprocessing.Pipe()
        writer = multiprocessing.Process(
            target=_die_inside_a_transaction, args=(path, child))
        writer.start()
        assert parent.poll(5), "writer never entered its transaction"
        parent.recv()
        writer.terminate()
        writer.join(5)
        assert not writer.is_alive()

        recovered = Journal(path)
        try:
            assert [event.payload for event in recovered.since("s1")] == [
                {"committed": True}
            ]
        finally:
            recovered.close()

    def test_an_unknown_schema_version_is_refused(self, tmp_path):
        path = tmp_path / "future.db"
        db = sqlite3.connect(path)
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
        db.close()

        with pytest.raises(JournalError, match="unsupported"):
            Journal(path)
