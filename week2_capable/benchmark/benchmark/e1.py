"""Budgeted journey benchmark command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .config import RESULT_MODES, Repository, create_attempt
from .journeys import JOURNEYS
from .metrics import LEGACY_WEEK1_MOVES, LEGACY_WEEK1_TOTAL, week1_corpus
from .report import append_jsonl, read_rows, write_markdown
from .runner import Budget, BudgetError, prove_surface, run_attempt

PROFILES = ("direct-full", "direct-core", "hybrid-full", "hybrid-core")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spend", action="store_true", help="authorize paid J1 attempts"
    )
    parser.add_argument("--cap", type=float, help="cumulative dollar cap")
    parser.add_argument(
        "--runs",
        type=_positive_integer,
        default=1,
        help="target number of priced journey samples in this output ledger",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="runtime result directory, default .boukensha/benchmarks/e1",
    )
    parser.add_argument(
        "--result-mode",
        choices=RESULT_MODES,
        default="full",
        help="model-facing gateway result shape",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default="direct-full",
        help="validated gateway tool surface",
    )
    parser.add_argument(
        "--model",
        help="model identifier retained in the isolated attempt overlay",
    )
    parser.add_argument(
        "--compaction-threshold",
        type=float,
        help="context-window fraction retained in the isolated attempt overlay",
    )
    parser.add_argument(
        "--journey",
        choices=tuple(JOURNEYS),
        default="J1",
        help="evidence-judged game objective",
    )
    parser.add_argument(
        "--player-profile",
        help="configured player profile, defaults to gateway.connection.player_profile",
    )
    parser.add_argument(
        "--max-iterations",
        type=_positive_integer,
        help="per-sample agent iteration ceiling",
    )
    parser.add_argument(
        "--max-sample-cost",
        type=float,
        help="per-sample agent spend ceiling",
    )
    parser.add_argument(
        "--attempt-timeout",
        type=float,
        help="per-sample wall-clock ceiling in seconds",
    )
    parser.add_argument(
        "--count-attempts",
        action="store_true",
        help="count every launched attempt toward --runs, timeouts included",
    )
    parser.add_argument(
        "--warm",
        action="store_true",
        help="keep the player's knowledge and progress between attempts, "
             "relocating to the temple instead of resetting the baseline",
    )
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="enable one named capability in the attempt overlay, repeatable",
    )
    parser.add_argument(
        "--player",
        help="one-off player character, requires --password-stdin",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the selected player's password from standard input",
    )
    arguments = parser.parse_args(argv)
    if arguments.player and arguments.player_profile:
        parser.error("--player and --player-profile are mutually exclusive")
    if arguments.player and not arguments.password_stdin:
        parser.error("--player requires --password-stdin")
    journey = JOURNEYS[arguments.journey]
    repository = Repository.discover()
    proof = prove_surface(profile=arguments.profile)
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
    if proof.profile_id != arguments.profile or proof.advertised_tools < 1:
        parser.error("dry-run surface does not match the selected gateway profile")
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
    if any(row.result_mode != arguments.result_mode for row in prior):
        parser.error("an output ledger cannot mix model-facing result modes")
    if any(row.profile_id != arguments.profile for row in prior):
        parser.error("an output ledger cannot mix gateway profiles")
    if prior and arguments.runs == 1:
        parser.error(
            "the J1 live gate already has an attempt; additional samples need "
            "--runs with an explicit target and cap"
        )
    completed_samples = sum(row.aggregate_eligible for row in prior)
    if completed_samples >= arguments.runs:
        parser.error(
            f"the ledger already has {completed_samples} priced samples, target is "
            f"{arguments.runs}"
        )
    budget = Budget(arguments.cap, sum(row.cost_usd or 0 for row in prior))
    rows = list(prior)
    supplied_password = None
    if arguments.password_stdin:
        supplied_password = sys.stdin.readline().rstrip("\r\n")
        if not supplied_password:
            parser.error("--password-stdin received an empty password")
    def counted(material: list) -> int:
        if arguments.count_attempts:
            return len(material)
        return sum(row.aggregate_eligible for row in material)

    shared_config = None
    while counted(rows) < arguments.runs:
        run_number = len(rows) + 1
        attempt_id = _attempt_id(run_number, multiple=arguments.runs > 1)
        attempt_dir = (
            output / "attempts" / "warm" if arguments.warm
            else output / "attempts" / attempt_id
        )
        if arguments.warm and shared_config is not None:
            config = shared_config
        else:
            config = create_attempt(
            repository,
            attempt_dir,
            result_mode=arguments.result_mode,
            profile=arguments.profile,
            player_profile=arguments.player_profile,
            player_character=arguments.player,
            model=arguments.model,
            compaction_threshold=arguments.compaction_threshold,
            max_iterations=arguments.max_iterations,
            max_turn_cost=arguments.max_sample_cost,
            capabilities=tuple(arguments.capability),
            )
        if arguments.warm:
            shared_config = config
        runtime_environment = dict(os.environ)
        password = (
            supplied_password
            or repository.player_password(
                config.player_profile,
                config.player_password_env,
            )
        )
        if password:
            runtime_environment[config.player_password_env] = password
        shared_secret_file = repository.settings_dir / ".env"
        if shared_secret_file.is_file():
            runtime_environment["BOUKENSHA_ADMIN_SECRET_FILE"] = str(
                shared_secret_file
            )
        try:
            budget.require_headroom(config.max_turn_cost)
        except BudgetError as error:
            print(f"STOP: {error}")
            return 2

        row = run_attempt(
            repository=repository,
            config=config,
            journey=journey,
            attempt_id=attempt_id,
            proof=proof,
            environment=runtime_environment,
            timeout_seconds=arguments.attempt_timeout,
            warm=arguments.warm,
        )
        append_jsonl(ledger, row)
        rows.append(row)
        write_markdown(output / "report.md", rows, corpus=corpus)
        print(json.dumps(row.as_dict(), indent=2, sort_keys=True))

        if row.setup_failure:
            print("STOP: setup failed before a model call; fix it, then resume")
            return 2
        try:
            budget.record(row.cost_usd)
        except BudgetError as error:
            print(f"STOP: {error}")
            return 2

    if arguments.runs > 1:
        return 0
    return 0 if rows[-1].success else 1


def _positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("--runs must be at least 1")
    return number


def _attempt_id(run_number: int, *, multiple: bool) -> str:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{timestamp}-{run_number:02d}" if multiple else timestamp


if __name__ == "__main__":
    raise SystemExit(main())
