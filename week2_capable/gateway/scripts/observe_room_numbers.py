"""Record the game's own room numbers beside a run, for grading later.

    uv run python scripts/observe_room_numbers.py <gateway.db> <out.jsonl>

Follows a running session's journal, and whenever the character settles
in a place, asks the game on a separate immortal connection which room
that actually is. The playing agent has no part in this and no access to
the answer: it runs in another process, on another connection, writing
to another file.

What it produces is the answer key for asking whether the rooms we
believe are one room really are, without ever letting the agent read the
map it is supposed to earn.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

from mud_gateway.admin import AdminSession
from mud_gateway.journal import Journal
from mud_gateway.settings import GatewaySettings
from mud_gateway.truth import RoomNumbers


def _positions(journal: Journal, session: str, after: int):
    """Places the character settled in, newest last."""
    for event in journal.since(session, kind="position"):
        if event.seq <= after:
            continue
        payload = event.payload or {}
        yield event.seq, payload.get("place"), payload.get("title")


async def watch(db: pathlib.Path, out: pathlib.Path, poll: float) -> int:
    settings = GatewaySettings.load()
    journal = Journal(db)
    admin = AdminSession(
        Journal(out.with_name("observer-admin.db")),
        name=settings.admin_character,
        password=settings.admin_password or "",
        host=settings.host,
        port=settings.port,
    )
    profile = settings.player(settings.player_profile)
    numbers = RoomNumbers(admin, out, profile.character)
    await admin.open()
    seen: dict[str, int] = {}
    try:
        while True:
            for session in journal.sessions():
                cursor = seen.get(session, 0)
                for seq, place, title in _positions(journal, session, cursor):
                    seen[session] = seq
                    await numbers.observe(place, session, expected_title=title)
            await asyncio.sleep(poll)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await admin.close()
        journal.close()
    print(f"recorded {numbers.recorded}, skipped {numbers.skipped}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=pathlib.Path)
    parser.add_argument("out", type=pathlib.Path)
    parser.add_argument("--poll", type=float, default=1.0)
    args = parser.parse_args(argv)
    return asyncio.run(watch(args.journal, args.out, args.poll))


if __name__ == "__main__":
    raise SystemExit(main())
