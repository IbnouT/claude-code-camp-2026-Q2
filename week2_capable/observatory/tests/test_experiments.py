from __future__ import annotations

import json
from pathlib import Path

import pytest

from observatory_api.execution import (
    ExperimentExecutor,
    ExperimentRequestConflict,
)
from observatory_api.experiments import (
    fork_one_variable,
    remaining_queue,
    sample_queue,
    validate_definition,
)
from observatory_api.sources.comparison import (
    experiment_registry,
    rendering_definition,
)
from observatory_api.sources.benchmark import stable_run_id


def test_typed_registry_rejects_unknown_fields_and_spend_mismatch():
    definition = rendering_definition()
    first = definition.arms[0]
    changed = first.model_copy(
        update={"values": {**first.values, "unknown.flag": True}}
    )
    invalid = definition.model_copy(
        update={
            "arms": (changed, *definition.arms[1:]),
            "effective_max_spend_usd": 1,
        }
    )

    result = validate_definition(
        invalid,
        experiment_registry(),
        execution_available=True,
        local_spend_cap=100,
    )

    assert result.valid is False
    assert any("unregistered fields" in issue for issue in result.issues)
    assert any("Effective maximum spend" in issue for issue in result.issues)


def test_validator_allows_runner_supported_overlays_and_blocks_observe_only():
    definition = rendering_definition()
    first = definition.arms[0]
    supported = first.model_copy(
        update={
            "values": {
                **first.values,
                "tools.profile": "hybrid-core",
                "policy.max_iterations": 41,
            }
        }
    )
    supported_definition = definition.model_copy(
        update={"arms": (supported, *definition.arms[1:])}
    )

    supported_result = validate_definition(
        supported_definition,
        experiment_registry(),
        execution_available=True,
        local_spend_cap=100,
    )

    assert not any(
        "installed runner" in issue for issue in supported_result.issues
    )

    blocked = supported.model_copy(
        update={"values": {**supported.values, "memory.enabled": False}}
    )
    blocked_definition = definition.model_copy(
        update={"arms": (blocked, *definition.arms[1:])}
    )
    blocked_result = validate_definition(
        blocked_definition,
        experiment_registry(),
        execution_available=True,
        local_spend_cap=100,
    )

    assert any(
        "Persistent knowledge" in issue and "installed runner" in issue
        for issue in blocked_result.issues
    )


def test_one_variable_fork_preserves_parent_and_only_changes_selected_value():
    definition = rendering_definition()
    fork = fork_one_variable(
        definition,
        arm_id="minimal",
        feature_id="tools.profile",
        value="direct-core",
        registry=experiment_registry(),
    )

    assert fork.parent_definition_id == definition.id
    assert fork.changed_feature == "minimal:tools.profile"
    assert fork.version == definition.version + 1
    changed = next(arm for arm in fork.arms if arm.id == "minimal")
    assert changed.values["tools.profile"] == "direct-core"
    assert next(arm for arm in fork.arms if arm.id == "raw") == definition.arms[0]


def test_stop_and_resume_preserve_sample_identity_and_queue_order():
    definition = rendering_definition()
    queue = sample_queue(definition)
    completed = {queue[0], queue[1], queue[4]}

    resumed = remaining_queue(definition, completed)

    assert len(queue) == 30
    assert resumed == tuple(item for item in queue if item not in completed)
    assert sample_queue(definition) == queue


def test_executor_persists_idempotent_jobs_and_recovers_running_as_stopped(
    tmp_path,
):
    executor = ExperimentExecutor(
        tmp_path / "state",
        benchmark_root=tmp_path / "benchmarks",
        repository_root=tmp_path,
    )
    definition = rendering_definition()

    first = executor.create(
        request_id="request-42",
        definition=definition,
        player_profile="poucet",
        confirmed_max_spend_usd=definition.effective_max_spend_usd,
    )
    duplicate = executor.create(
        request_id="request-42",
        definition=definition,
        player_profile="poucet",
        confirmed_max_spend_usd=definition.effective_max_spend_usd,
    )
    first.state = "running"
    executor._persist(first)
    definition_path = (
        tmp_path
        / "state"
        / "definitions"
        / f"{definition.id}-v{definition.version}.json"
    )

    recovered = ExperimentExecutor(
        tmp_path / "state",
        benchmark_root=tmp_path / "benchmarks",
        repository_root=tmp_path,
    ).require(first.id)

    assert duplicate is first
    assert first.public()["definition"]["id"] == definition.id
    assert definition_path.is_file()
    assert len(first.samples) == 30
    assert recovered.state == "stopped"
    assert list(recovered.samples) == list(first.samples)


def test_executor_rejects_idempotency_reuse_for_a_different_request(tmp_path):
    executor = ExperimentExecutor(
        tmp_path / "state",
        benchmark_root=tmp_path / "benchmarks",
        repository_root=tmp_path,
    )
    definition = rendering_definition()
    executor.create(
        request_id="request-42",
        definition=definition,
        player_profile="alice",
        confirmed_max_spend_usd=definition.effective_max_spend_usd,
    )

    with pytest.raises(ExperimentRequestConflict):
        executor.create(
            request_id="request-42",
            definition=definition,
            player_profile="bob",
            confirmed_max_spend_usd=definition.effective_max_spend_usd,
        )


def test_executor_command_is_direct_argv_and_routes_evidence_to_sessions(
    tmp_path,
):
    executor = ExperimentExecutor(
        tmp_path / "state",
        benchmark_root=tmp_path / "benchmarks",
        repository_root=tmp_path,
    )
    definition = rendering_definition().model_copy(
        update={"repetitions_per_arm": 1, "effective_max_spend_usd": 1.8}
    )
    job = executor.create(
        request_id="request-99",
        definition=definition,
        player_profile="alice",
        confirmed_max_spend_usd=definition.effective_max_spend_usd,
    )
    output = tmp_path / "benchmarks" / "observatory-request-99-raw-001"
    command = executor.sample_command(
        job=job,
        output=output,
        result_mode="raw",
        effective_config={
            **definition.arms[0].values,
            "policy.max_iterations": 41,
        },
    )

    assert command[:2] == ("uv", "run")
    assert "--spend" in command
    assert command[command.index("--player-profile") + 1] == "alice"
    assert command[command.index("--result-mode") + 1] == "raw"
    assert command[command.index("--profile") + 1] == "direct-full"
    assert command[command.index("--model") + 1] == "claude-haiku-4-5"
    assert command[command.index("--compaction-threshold") + 1] == "0.85"
    assert command[command.index("--max-iterations") + 1] == "41"
    assert command[command.index("--max-sample-cost") + 1] == "0.6"
    assert command[command.index("--output-dir") + 1] == str(output)
    assert not any("|" in argument or ";" in argument for argument in command)
    persisted = json.loads(
        (tmp_path / "state" / "jobs" / job.id / "job.json").read_text()
    )
    assert persisted["definition"]["id"] == definition.id


async def test_executor_retains_success_as_a_standard_sessions_run(
    tmp_path,
    monkeypatch,
):
    executor = ExperimentExecutor(
        tmp_path / "state",
        benchmark_root=tmp_path / "benchmarks",
        repository_root=tmp_path,
    )
    definition = rendering_definition().model_copy(
        update={"repetitions_per_arm": 1, "effective_max_spend_usd": 1.8}
    )
    job = executor.create(
        request_id="request-success",
        definition=definition,
        player_profile="alice",
        confirmed_max_spend_usd=definition.effective_max_spend_usd,
    )
    sample = next(iter(job.samples.values()))

    class Process:
        pid = 12345
        returncode = 0

        async def wait(self):
            return 0

    async def create_process(*command, **_options):
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "attempts.jsonl").write_text(
            json.dumps(
                {
                    "attempt_id": "20260730-001",
                    "success": True,
                    "setup_failure": False,
                    "cost_usd": 0.12,
                    "iterations": 11,
                    "tool_calls": 17,
                    "stop_reason": "completed",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return Process()

    monkeypatch.setattr(
        "observatory_api.execution.asyncio.create_subprocess_exec",
        create_process,
    )
    await executor._run_sample(job, sample)

    ledger_name = f"observatory-{job.id}-{sample['id']}"
    assert sample["state"] == "success"
    assert sample["cost_usd"] == 0.12
    assert sample["turns"] == 11
    assert sample["calls"] == 17
    assert sample["run_id"] == stable_run_id(ledger_name, "20260730-001")
