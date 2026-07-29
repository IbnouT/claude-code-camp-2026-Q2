"""Verify deterministic, secret-free replay of retained gateway journals."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mud_gateway.journal import Journal
from mud_gateway.stream import EventHub, canonical_wire


def gate(path: Path, secret: bytes | None) -> int:
    journal = Journal(path)
    hub = EventHub(journal)
    failures: list[str] = []
    events = 0
    wire_bytes = 0
    session_count = 0
    try:
        sessions = journal.sessions()
        session_count = len(sessions)
        for session in sessions:
            first = list(hub.replay(session))
            second = list(hub.replay(session))
            if first != second:
                failures.append(f"{session}: event replay changed")
            ids = [int(frame.splitlines()[0].split(": ", 1)[1]) for frame in first]
            if ids != sorted(ids):
                failures.append(f"{session}: event replay is unordered")
            wire = canonical_wire(journal, session)
            if wire != canonical_wire(journal, session):
                failures.append(f"{session}: wire replay changed")
            payload = "".join(first).encode() + wire
            if secret and secret in payload:
                failures.append(f"{session}: credential reached replay")
            events += len(first)
            wire_bytes += len(wire)
    finally:
        hub.close()
        journal.close()

    print(f"  sessions   : {session_count}")
    print(f"  events     : {events}")
    print(f"  wire bytes : {wire_bytes}")
    for failure in failures:
        print(f"  FAIL: {failure}")
    print(f"\n  STREAM SMOKE: {'PASS' if not failures else 'FAIL'}")
    return 0 if not failures else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    arguments = parser.parse_args()
    password = os.environ.get("MUD_PASSWORD")
    raise SystemExit(
        gate(
            arguments.journal,
            None if password is None else password.encode("latin-1"),
        )
    )


if __name__ == "__main__":
    main()
