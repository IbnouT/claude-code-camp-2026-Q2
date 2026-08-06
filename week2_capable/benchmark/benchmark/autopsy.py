"""Failure-inventory report over a batch of judged journey attempts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from .journeys import flatten_payload
from .metrics import read_gateway, read_jsonl

SIGNATURES: dict[str, re.Pattern[str]] = {
    "death": re.compile(r"you are dead|r\.i\.p\.", re.IGNORECASE),
    "exhaustion": re.compile(r"too exhausted", re.IGNORECASE),
    "darkness": re.compile(
        r"it is pitch black|too dark to tell", re.IGNORECASE
    ),
    "hunger": re.compile(r"you are hungry", re.IGNORECASE),
    "thirst": re.compile(r"you are thirsty", re.IGNORECASE),
    "attacked": re.compile(
        r"\b(?:hits|attacks|pierces|slashes|pounds|claws) you\b",
        re.IGNORECASE,
    ),
    "fled": re.compile(r"you flee|panic, and attempt to flee", re.IGNORECASE),
    "game_menu": re.compile(r"0\)\s*exit from tbamud", re.IGNORECASE),
    "minotaur_seen": re.compile(r"\bmassive minotaur\b", re.IGNORECASE),
    "minotaur_killed": re.compile(
        r"massive minotaur is dead|massive minotaur'?s death cry",
        re.IGNORECASE,
    ),
}


def classify(events: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count failure-signature hits over retained gateway observations."""
    counts: Counter[str] = Counter()
    for event in events:
        if event.get("kind") != "observation":
            continue
        payload = event.get("payload")
        text = flatten_payload(payload if isinstance(payload, dict) else {})
        for line in text.splitlines():
            for name, pattern in SIGNATURES.items():
                if pattern.search(line):
                    counts[name] += 1
    return dict(counts)


def report(output_dir: Path) -> dict[str, Any]:
    """Aggregate one batch ledger into a failure-inventory report."""
    rows = read_jsonl(output_dir / "attempts.jsonl")
    attempts: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for row in rows:
        journal = Path(str(row.get("gateway_journal")))
        signatures = (
            classify(read_gateway(journal)) if journal.is_file() else {}
        )
        for name, count in signatures.items():
            totals[name] += count
        error = row.get("error") or ""
        attempts.append({
            "attempt_id": row.get("attempt_id"),
            "status": row.get("status"),
            "success": row.get("success"),
            "timed_out": "attempt timeout" in error,
            "cost_usd": row.get("cost_usd"),
            "model_calls": row.get("model_calls"),
            "wall_ms": row.get("wall_ms"),
            "signatures": signatures,
        })
    finished = [row for row in attempts if row["status"] == "complete"]
    return {
        "attempts": attempts,
        "summary": {
            "attempts": len(attempts),
            "complete": len(finished),
            "successes": sum(bool(row["success"]) for row in attempts),
            "timeouts": sum(row["timed_out"] for row in attempts),
            "deaths": sum(
                bool(row["signatures"].get("death")) for row in attempts
            ),
            "minotaur_seen": sum(
                bool(row["signatures"].get("minotaur_seen"))
                for row in attempts
            ),
            "total_cost_usd": round(
                sum(row["cost_usd"] or 0 for row in attempts), 6
            ),
            "signature_totals": dict(totals),
        },
    }


def render_markdown(findings: dict[str, Any]) -> str:
    summary = findings["summary"]
    lines = [
        "# Mission autopsy",
        "",
        f"{summary['attempts']} attempts · "
        f"{summary['successes']} succeeded · "
        f"{summary['timeouts']} timed out · "
        f"{summary['deaths']} died · "
        f"minotaur seen in {summary['minotaur_seen']} · "
        f"${summary['total_cost_usd']:.4f} total",
        "",
        "| Attempt | Status | Success | Timeout | Cost | Calls | Signatures |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in findings["attempts"]:
        marks = ", ".join(
            f"{name}×{count}"
            for name, count in sorted(row["signatures"].items())
        ) or "none"
        cost = row["cost_usd"]
        lines.append(
            f"| {row['attempt_id']} | {row['status']} "
            f"| {'yes' if row['success'] else 'no'} "
            f"| {'yes' if row['timed_out'] else 'no'} "
            f"| {'' if cost is None else f'${cost:.4f}'} "
            f"| {row['model_calls']} | {marks} |"
        )
    lines += [
        "",
        "## Signature totals",
        "",
        "| Signature | Lines |",
        "| --- | ---: |",
        *(
            f"| {name} | {count} |"
            for name, count in sorted(
                summary["signature_totals"].items(),
                key=lambda item: -item[1],
            )
        ),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir",
        type=Path,
        help="benchmark output directory holding attempts.jsonl",
    )
    arguments = parser.parse_args(argv)
    findings = report(arguments.output_dir)
    (arguments.output_dir / "autopsy.json").write_text(
        json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8"
    )
    (arguments.output_dir / "autopsy.md").write_text(
        render_markdown(findings), encoding="utf-8"
    )
    print(json.dumps(findings["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
