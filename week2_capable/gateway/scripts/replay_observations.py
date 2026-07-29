"""Replay retained sessions through the observation parser."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Iterator

from mud_gateway.observe import Coverage, WireReference, parse
from mud_gateway.position import PositionTracker


def jsonl_frames(path: Path) -> Iterator[tuple[str, int, bytes, str | None]]:
    calls: dict[str, dict[str, object]] = {}
    for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("phase") == "prompt":
            for message in event.get("messages", []):
                for content in message.get("content", []):
                    if content.get("type") == "tool_use":
                        calls[content["id"]] = content.get("input", {})
        if event.get("phase") != "tool_result" or not isinstance(event.get("result"), str):
            continue
        move = None
        if str(event.get("name", "")).endswith("__move"):
            arguments = calls.get(str(event.get("tool_use_id")), {})
            candidate = arguments.get("direction")
            if isinstance(candidate, str):
                move = candidate
        yield path.name, number, event["result"].encode("latin-1"), move


def database_frames(path: Path) -> Iterator[tuple[str, int, bytes, None]]:
    uri = f"file:{path.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as database:
        rows = database.execute(
            "SELECT e.seq, b.body FROM events e "
            "JOIN blobs b ON b.digest = json_extract(e.payload, '$.digest') "
            "WHERE e.kind = 'wire' "
            "AND json_extract(e.payload, '$.direction') = 'in' "
            "ORDER BY e.seq"
        )
        for sequence, body in rows:
            yield path.name, int(sequence), bytes(body), None


def replay(root: Path) -> dict[str, object]:
    coverage = Coverage()
    sessions: set[str] = set()
    positions: Counter[str] = Counter()
    frames = 0

    paths = sorted((root / "sessions").glob("*.jsonl"))
    paths += sorted((root / "gateway").glob("*.db"))
    for path in paths:
        tracker = PositionTracker()
        source = jsonl_frames(path) if path.suffix == ".jsonl" else database_frames(path)
        for session, sequence, raw, move in source:
            sessions.add(f"{path.parent.name}/{session}")
            frames += 1
            reference = WireReference.from_bytes(
                f"{path.parent.name}/{session}", sequence, sequence, raw
            )
            observations = parse(raw, reference)
            coverage.add(observations)
            if move:
                tracker.moving(move)
            position = tracker.observe(observations)
            positions[position.confidence.value] += 1

    return {
        "recordings": len(paths),
        "sessions": len(sessions),
        "frames": frames,
        "lines": coverage.lines,
        "typed": coverage.typed,
        "parse_miss_rate": round(coverage.miss_rate, 6),
        "by_kind": dict(sorted(coverage.by_kind.items())),
        "position_confidence": dict(sorted(positions.items())),
        "residual_samples": coverage.unparsed_samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recordings",
        type=Path,
        default=Path(__file__).resolve().parents[3] / ".boukensha",
    )
    arguments = parser.parse_args()
    print(json.dumps(replay(arguments.recordings), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

