"""Discover runtime sessions and import legacy flat evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .config import Config
from .runtime import SessionRegistry, import_legacy_session


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="boukensha-sessions")
    subcommands = parser.add_subparsers(dest="command", required=True)

    listing = subcommands.add_parser("list", help="list registered sessions")
    listing.add_argument("--player-profile")
    listing.add_argument("--json", action="store_true")

    importing = subcommands.add_parser(
        "import-legacy",
        help="copy one flat JSONL recording into a player profile",
    )
    importing.add_argument("source", type=Path)
    importing.add_argument("--player-profile", required=True)
    importing.add_argument("--character", required=True)

    arguments = parser.parse_args(argv)
    config = Config()
    if arguments.command == "import-legacy":
        identity = import_legacy_session(
            config.dir,
            arguments.source,
            player_id=arguments.player_profile,
            character=arguments.character,
        )
        print(identity.session_id)
        return 0

    registry = SessionRegistry(config.dir)
    try:
        rows = registry.sessions(player_id=arguments.player_profile)
    finally:
        registry.close()
    if arguments.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("No registered sessions.")
        return 0
    for row in rows:
        print(
            f"{row['session_id']}  {row['player_id']}  "
            f"{row['character']}  {row['state']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
