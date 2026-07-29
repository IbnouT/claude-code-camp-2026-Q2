"""Apply two live resets and compare mortal-observable state."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from admin_process.reset import ResetPlan
from mud_gateway.admin import AdminSession
from mud_gateway.journal import Journal
from mud_gateway.session import Session


async def gate(
    *,
    player_name: str,
    player_password: str,
    admin_name: str,
    admin_password: str,
    database: Path,
) -> int:
    journal = Journal(database)
    player = Session(journal, name=player_name, password=player_password)
    admin = AdminSession(journal, name=admin_name, password=admin_password)
    try:
        await player.open()
        await admin.open()
        plan = ResetPlan()
        first = await plan.apply(admin, player, player_name)
        second = await plan.apply(admin, player, player_name)
        differences = first.state.differences(second.state)
        passed = first.ok and second.ok and not differences
        print(f"  first reset  : ok={first.ok} unread={first.state.unread}")
        print(f"  second reset : ok={second.ok} unread={second.state.unread}")
        print(f"  differences  : {differences}")
        print(f"\n  RESET SMOKE: {'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    finally:
        await admin.close()
        await player.close()
        journal.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", default=os.environ.get("MUD_NAME", "poucet"))
    parser.add_argument("--admin", default=os.environ.get("MUD_ADMIN_NAME", "admin"))
    parser.add_argument("--db", type=Path, required=True)
    arguments = parser.parse_args()
    player_password = os.environ.get("MUD_PASSWORD")
    admin_password = os.environ.get("MUD_ADMIN_PASSWORD")
    if not player_password or not admin_password:
        parser.error("MUD_PASSWORD and MUD_ADMIN_PASSWORD are required")
    raise SystemExit(
        asyncio.run(
            gate(
                player_name=arguments.player,
                player_password=player_password,
                admin_name=arguments.admin,
                admin_password=admin_password,
                database=arguments.db,
            )
        )
    )


if __name__ == "__main__":
    main()

