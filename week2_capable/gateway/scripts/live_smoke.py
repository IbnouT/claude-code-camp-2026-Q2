"""Smoke-test the gateway against the live game.

    uv run python scripts/live_smoke.py

Four things have to hold:

1. The session logs in, walking all four entry steps.
2. Commands come back complete, delimited by the vitals prompt.
3. The journalled wire log reconstructs the traffic BYTE FOR BYTE, so anything derived later
   can be traced to the bytes that caused it.
4. No credential appears anywhere in the journal, in any event, at any level.

Not part of the hermetic suite, because whether a login works can only be answered by the
server. The hermetic suite covers framing, ordering and redaction with no game running.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

from mud_gateway.journal import Journal
from mud_gateway.session import Session
from mud_gateway.wire import PROMPT


async def gate(player: str, password: str, db: pathlib.Path) -> int:
    journal = Journal(db)
    session = Session(journal, name=player, password=password)
    failures: list[str] = []
    try:
        await session.open()
        print(f"  login    : {session}")
        if not session.logged_in:
            failures.append("did not reach a prompt")

        for line in ("look", "score", "exits"):
            reply = await session.command(line)
            first = next((row for row in reply.text.split("\n") if row.strip()), "")
            print(f"  {line:8} : complete={reply.complete} seq={reply.seq} "
                  f"{first.strip()[:46]!r}")
            if not reply.complete:
                failures.append(f"{line} did not reach a prompt")

        # 3. Byte-exact reconstruction, from the journal alone.
        wire = journal.since(session.id, kind="wire")
        rebuilt_in = b"".join(
            journal.get_blob(event.payload["digest"]) or b""
            for event in wire
            if event.payload["direction"] == "in" and event.payload["digest"])
        live_in = b"".join(e.payload for e in session.transport.events
                           if e.direction.value == "in")
        print(f"  wire     : {len(wire)} events, "
              f"{len(rebuilt_in):,} inbound bytes rebuilt from the journal")
        if rebuilt_in != live_in:
            failures.append(f"replay mismatch: {len(rebuilt_in)} vs {len(live_in)} bytes")

        # And the reconstruction has to be usable, not merely equal in length.
        if PROMPT.search(rebuilt_in) is None:
            failures.append("the rebuilt stream contains no prompt")

        # 4. No credential anywhere.
        secret = password.encode("latin-1")
        leaked = [event.seq for event in journal.since(session.id)
                  if secret in repr(event.payload).encode("latin-1")]
        blobs = [event.seq for event in wire
                 if event.payload.get("digest")
                 and secret in (journal.get_blob(event.payload["digest"]) or b"")]
        print(f"  secrets  : {len(leaked)} in payloads, {len(blobs)} in stored bodies")
        if leaked or blobs:
            failures.append(f"credential leaked in events {leaked + blobs}")

        redacted = [e for e in session.transport.events if e.redacted]
        print(f"  redacted : {len(redacted)} event(s), length preserved="
              f"{[len(e.payload) for e in redacted]}")
        if not redacted:
            failures.append("the password line was not recorded as redacted")
    finally:
        await session.close()
        exported = journal.export_jsonl(session.id, db.parent / f"{session.id}.jsonl")
        print(f"  export   : {exported} events to {session.id}.jsonl")
        print(f"  journal  : {journal}")
        journal.close()

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
    print(f"  LIVE SMOKE: {'PASS' if not failures else 'FAIL'}")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player", default="poucet")
    parser.add_argument("--password", default=os.environ.get("MUD_PASSWORD"))
    parser.add_argument("--db", default="../../.boukensha/gateway/live-smoke.db")
    args = parser.parse_args(argv)
    if not args.password:
        parser.error("--password or MUD_PASSWORD is required")
    return asyncio.run(gate(args.player, args.password, pathlib.Path(args.db).resolve()))


if __name__ == "__main__":
    sys.exit(main())
