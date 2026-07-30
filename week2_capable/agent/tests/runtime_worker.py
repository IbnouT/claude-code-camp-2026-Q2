"""Hermetic subprocess used by the multi-player isolation gate."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

from boukensha.logger import Logger
from boukensha.runtime import CharacterAlreadyRunning, RuntimeSession


def main() -> int:
    config_dir = Path(sys.argv[1])
    player_id = sys.argv[2]
    character = sys.argv[3]
    cost = float(sys.argv[4])
    tokens = int(sys.argv[5])
    try:
        runtime = RuntimeSession.create(
            config_dir,
            player_id=player_id,
            character=character,
        )
    except CharacterAlreadyRunning:
        print(json.dumps({"error": "CharacterAlreadyRunning"}), flush=True)
        return 23

    environment = runtime.child_environment(
        parent=os.environ,
        secrets={f"PLAYER_{player_id.upper()}": f"{player_id}-canary"},
    )
    old = dict(os.environ)
    os.environ.clear()
    os.environ.update(environment)
    try:
        with Logger() as logger:
            logger.turn_end(
                "completed",
                1,
                tokens=tokens,
                input_tokens=tokens - 1,
                output_tokens=1,
                cost_usd=cost,
            )
        database = sqlite3.connect(runtime.paths.gateway_journal)
        database.execute(
            "CREATE TABLE ownership (player_id TEXT, session_id TEXT)"
        )
        database.execute(
            "INSERT INTO ownership VALUES (?, ?)",
            (player_id, runtime.identity.session_id),
        )
        database.commit()
        database.close()
    finally:
        os.environ.clear()
        os.environ.update(old)

    runtime.running(os.getpid())
    print(
        json.dumps(
            {
                "player_id": player_id,
                "session_id": runtime.identity.session_id,
                "session_dir": str(runtime.paths.session_dir),
                "secret_names": sorted(
                    key for key in environment if key.startswith("PLAYER_")
                ),
            }
        ),
        flush=True,
    )
    sys.stdin.readline()
    runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
