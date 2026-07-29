"""Budgeted E1 command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .config import Repository, create_attempt
from .journeys import J1
from .metrics import LEGACY_WEEK1_MOVES, LEGACY_WEEK1_TOTAL, week1_corpus
from .report import append_jsonl, read_rows, write_markdown
from .runner import Budget, BudgetError, prove_surface, run_attempt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spend", action="store_true", help="authorize one paid J1 attempt")
    parser.add_argument("--cap", type=float, help="cumulative dollar cap")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="runtime result directory, default .boukensha/benchmarks/e1",
    )
    arguments = parser.parse_args(argv)
    repository = Repository.discover()
    proof = prove_surface(profile="direct-full")
    corpus = week1_corpus(repository.week1_sessions)
    summary = {
        "surface": {
            "profile": proof.profile_id,
            "tools": proof.advertised_tools,
            "schema_bytes": proof.schema_bytes,
            "schema_token_estimate": proof.schema_token_estimate,
            "capability_digest": proof.capability_digest,
        },
        "week1": {
            "executed_total": corpus.executed_total,
            "executed_moves": corpus.executed_by_tool.get("move", 0),
            "prompt_confirmed_total": corpus.confirmed_total,
            "prompt_confirmed_moves": corpus.confirmed_by_tool.get("move", 0),
            "legacy_total": LEGACY_WEEK1_TOTAL,
            "legacy_moves": LEGACY_WEEK1_MOVES,
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if proof.profile_id != "direct-full" or proof.advertised_tools != 25:
        parser.error("dry-run surface is not direct-full with 25 tools")
    if corpus.executed_total != 451 or corpus.executed_by_tool.get("move") != 316:
        parser.error("tracked Week 1 executed-call corpus drifted")
    if corpus.confirmed_total != 447 or corpus.confirmed_by_tool.get("move") != 314:
        parser.error("tracked Week 1 prompt-confirmed corpus drifted")
    if not arguments.spend:
        return 0
    if arguments.cap is None:
        parser.error("--spend requires --cap")

    output = arguments.output_dir or repository.settings_dir / "benchmarks" / "e1"
    ledger = output / "attempts.jsonl"
    prior = read_rows(ledger)
    if prior:
        parser.error(
            "the J1 live gate already has an attempt; additional samples need "
            "a separately authorized output directory and cap"
        )
    budget = Budget(arguments.cap, sum(row.cost_usd or 0 for row in prior))
    attempt_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    attempt_dir = output / "attempts" / attempt_id
    config = create_attempt(repository, attempt_dir)
    try:
        budget.require_headroom(config.max_turn_cost)
    except BudgetError as error:
        parser.error(str(error))

    row = run_attempt(
        repository=repository,
        config=config,
        journey=J1,
        attempt_id=attempt_id,
        proof=proof,
        environment=os.environ,
    )
    append_jsonl(ledger, row)
    rows = [*prior, row]
    write_markdown(output / "report.md", rows, corpus=corpus)
    try:
        budget.record(row.cost_usd)
    except BudgetError as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps(row.as_dict(), indent=2, sort_keys=True))
    return 0 if row.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
