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
    rows = [_with_control_state(row) for row in rows]
    if arguments.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("No registered sessions.")
        return 0
    for row in rows:
        print(
            f"{row['session_id']}  {row['player_id']}  "
            f"{row['character']}  process={row['process_state']}  "
            f"control={row['control_state'] or 'not-captured'}"
        )
    return 0


def _with_control_state(row: dict) -> dict:
    """Join launcher process state with the gateway's live control projection."""
    enriched = dict(row)
    enriched["process_state"] = row["state"]
    enriched["process_state_source"] = "launcher_registry"
    projection = Path(str(row["session_dir"])) / "control-state.json"
    control_state = None
    if projection.is_file():
        try:
            value = json.loads(projection.read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("state"), str):
                control_state = value["state"]
        except (OSError, json.JSONDecodeError):
            control_state = "capture_gap"
    enriched["control_state"] = control_state
    enriched["control_state_source"] = (
        "gateway_projection" if control_state is not None else "not_captured"
    )
    return enriched


if __name__ == "__main__":
    raise SystemExit(main())
