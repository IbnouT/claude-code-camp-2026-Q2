"""Supervise one isolated boukensha agent session."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .config import Config
from .errors import ConfigError
from .objective import ObjectiveContext
from .runtime import CharacterAlreadyRunning, RuntimeSession
from .version import __version__

PROVIDER_SECRET_NAMES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama_cloud": "OLLAMA_API_KEY",
    "openai": "OPENAI_API_KEY",
}
STOP_TIMEOUT_SECONDS = 10.0


def main(argv: Sequence[str] | None = None) -> int:
    """Create the runtime envelope, spawn the agent, and own its lifecycle."""
    parser = argparse.ArgumentParser(
        prog="boukensha",
        description="Launch one isolated boukensha MUD agent session.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"boukensha {__version__}",
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="use the plain terminal REPL",
    )
    parser.add_argument(
        "--player-profile",
        help="configured player profile, default gateway.connection.player_profile",
    )
    parser.add_argument(
        "--task-stdin",
        action="store_true",
        help="run one task read from stdin instead of opening the interactive UI",
    )
    parser.add_argument(
        "--initial-task-stdin",
        action="store_true",
        help=(
            "read the first REPL task from stdin, then keep the plain REPL open"
        ),
    )
    parser.add_argument(
        "--reset-baseline",
        metavar="NAME@VERSION",
        help="reset the selected authenticated session before the first model call",
    )
    parser.add_argument(
        "--relocate-temple",
        action="store_true",
        help="move the selected player to the Temple before the first instruction",
    )
    parser.add_argument(
        "--objective-title",
        help="concise authored objective title retained for observers",
    )
    parser.add_argument(
        "--objective-clue",
        help="optional authored location or strategy clue",
    )
    parser.add_argument(
        "--objective-source-kind",
        choices=("benchmark", "operator"),
        default="operator",
        help="source of the structured objective metadata",
    )
    parser.add_argument(
        "--objective-revision",
        type=int,
        default=1,
        help="positive authored objective revision",
    )
    arguments = parser.parse_args(argv)
    if arguments.task_stdin and arguments.initial_task_stdin:
        parser.error("--task-stdin and --initial-task-stdin are mutually exclusive")
    if arguments.initial_task_stdin and not arguments.no_tui:
        parser.error("--initial-task-stdin requires --no-tui")
    task = sys.stdin.read().strip() if arguments.task_stdin else None
    if arguments.task_stdin and not task:
        parser.error("--task-stdin received an empty task")
    if arguments.reset_baseline and arguments.relocate_temple:
        parser.error("--reset-baseline and --relocate-temple are mutually exclusive")
    if (
        not arguments.task_stdin
        and (
            arguments.objective_title is not None
            or arguments.objective_clue is not None
            or arguments.objective_source_kind != "operator"
            or arguments.objective_revision != 1
        )
    ):
        parser.error("objective metadata requires --task-stdin")
    try:
        objective = (
            ObjectiveContext.create(
                task or "",
                title=arguments.objective_title,
                clue=arguments.objective_clue,
                source_kind=arguments.objective_source_kind,
                revision=arguments.objective_revision,
            )
            if task is not None
            else None
        )
    except ValueError as error:
        parser.error(str(error))

    config = Config()
    player_id = arguments.player_profile or config.mud_player_profile
    profile = config.mud_profile(player_id)
    if not profile:
        raise ConfigError(f"unknown player profile {player_id!r}")
    character = str(profile.get("character") or player_id)
    experiment_id, run_id = _experiment_correlation(os.environ)

    try:
        runtime = RuntimeSession.create(
            config.dir,
            player_id=player_id,
            character=character,
            experiment_id=experiment_id,
            run_id=run_id,
        )
    except CharacterAlreadyRunning as error:
        parser.error(str(error))

    child_args = [sys.executable, "-m", "boukensha.runtime_child"]
    if arguments.no_tui:
        child_args.append("--no-tui")
    if arguments.initial_task_stdin:
        child_args.append("--initial-task-stdin")
    secrets = _child_secrets(config, player_id, profile)
    child_env = runtime.child_environment(
        parent=os.environ,
        secrets=secrets,
    )
    admin_secret_file = Path(
        os.environ.get("BOUKENSHA_ADMIN_SECRET_FILE", config.dir / ".env")
    ).expanduser()
    if admin_secret_file.is_file():
        child_env["BOUKENSHA_ADMIN_SECRET_FILE"] = str(admin_secret_file)
    if task is not None:
        child_env["BOUKENSHA_LAUNCH_TASK"] = task
    if objective is not None:
        child_env["BOUKENSHA_OBJECTIVE_CONTEXT"] = objective.encode()
    if arguments.reset_baseline:
        child_env["BOUKENSHA_RESET_BASELINE"] = arguments.reset_baseline
        raw_timeout = config.dig(
            "gateway",
            "reset",
            "client_timeout_seconds",
        )
        try:
            reset_timeout = 45.0 if raw_timeout is None else float(raw_timeout)
        except (TypeError, ValueError) as error:
            raise ConfigError(
                "gateway.reset.client_timeout_seconds must be a number"
            ) from error
        if reset_timeout <= 0:
            raise ConfigError(
                "gateway.reset.client_timeout_seconds must be positive"
            )
        child_env["BOUKENSHA_RESET_CLIENT_TIMEOUT"] = str(reset_timeout)
    if arguments.relocate_temple:
        child_env["BOUKENSHA_RELOCATE_TEMPLE"] = "1"
    process: subprocess.Popen | None = None
    exit_code = 1
    try:
        process = subprocess.Popen(
            child_args,
            env=child_env,
            start_new_session=True,
        )
        runtime.running(process.pid)
        exit_code = _wait(process)
        return exit_code
    finally:
        if process is not None and process.poll() is None:
            runtime.terminate_process_group(process.pid)
            try:
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                runtime.terminate_process_group(process.pid, signal.SIGKILL)
                process.wait()
            exit_code = process.returncode
        runtime.close(exit_code=exit_code)


def _child_secrets(
    config: Config,
    player_id: str,
    profile: dict,
) -> dict[str, str]:
    names = {str(profile.get("password_env") or "MUD_PASSWORD")}
    task = config.tasks("player") or {}
    provider = str(task.get("provider") or "")
    provider_name = PROVIDER_SECRET_NAMES.get(provider)
    if provider_name:
        names.add(provider_name)
    return {
        name: value
        for name in names
        if (value := config.secret(name, profile_id=player_id))
    }


def _experiment_correlation(
    environment: Mapping[str, str],
) -> tuple[str | None, str | None]:
    experiment_id = environment.get("BOUKENSHA_EXPERIMENT_ID")
    run_id = environment.get("BOUKENSHA_RUN_ID")
    if bool(experiment_id) != bool(run_id):
        raise ConfigError(
            "experiment identity requires both BOUKENSHA_EXPERIMENT_ID "
            "and BOUKENSHA_RUN_ID"
        )
    return experiment_id, run_id


def _wait(process: subprocess.Popen) -> int:
    try:
        return process.wait()
    except KeyboardInterrupt:
        os.killpg(process.pid, signal.SIGINT)
        return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
