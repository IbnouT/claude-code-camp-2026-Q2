from __future__ import annotations

import asyncio

import pytest

from observatory_v3_backend.execution import (
    ExperimentExecutor,
    ExperimentRequestConflict,
    SampleResult,
)
from observatory_v3_backend.experiments import (
    fork_one_variable,
    remaining_queue,
    sample_queue,
    validate_definition,
)
from observatory_v3_backend.sources.comparison import (
    experiment_registry,
    rendering_definition,
)
from observatory_v3_backend.storage_executor import StorageExecutor


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

    assert not any("installed runner" in issue for issue in supported_result.issues)

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
        storage=StorageExecutor(capacity=1),
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
    recovered_executor = ExperimentExecutor(
        tmp_path / "state",
        benchmark_root=tmp_path / "benchmarks",
        storage=StorageExecutor(capacity=1),
        repository_root=tmp_path,
    )
    asyncio.run(recovered_executor.reconcile())
    recovered = recovered_executor.require(first.id)

    assert duplicate.id == first.id
    assert first.public()["definition"]["id"] == definition.id
    assert (tmp_path / "state" / "experiments-v1.sqlite3").is_file()
    assert len(first.samples) == 30
    assert recovered.state == "stopped"
    assert list(recovered.samples) == list(first.samples)


def test_executor_rejects_idempotency_reuse_for_a_different_request(tmp_path):
    executor = ExperimentExecutor(
        tmp_path / "state",
        benchmark_root=tmp_path / "benchmarks",
        storage=StorageExecutor(capacity=1),
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
        storage=StorageExecutor(capacity=1),
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
    persisted = executor.require(job.id)
    assert persisted.definition.id == definition.id


async def test_executor_retains_success_as_a_standard_sessions_run(
    tmp_path,
):
    launches: list[str] = []

    class Runner:
        def dry_run(self, job, sample):
            return (
                ("runner", "--sample", sample.id),
                {
                    "BOUKENSHA_EXPERIMENT_ID": job.id,
                    "BOUKENSHA_RUN_ID": sample.id,
                },
            )

        async def run(self, _job, sample):
            launches.append(sample.id)
            return SampleResult(
                state="success",
                detail="completed",
                cost_usd=0.12,
                turns=11,
                calls=17,
            )

        async def stop(self, _job_id):
            return None

    executor = ExperimentExecutor(
        tmp_path / "state",
        benchmark_root=tmp_path / "benchmarks",
        storage=StorageExecutor(capacity=1),
        repository_root=tmp_path,
        runner=Runner(),
        session_resolver=lambda _experiment_id, run_id: f"session-{run_id}",
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
    await executor.start(job.id)
    task = executor.tasks[job.id]
    await task
    retained = executor.require(job.id)
    sample = next(iter(retained.samples.values()))

    assert sample.state == "success"
    assert sample.cost_usd == 0.12
    assert sample.turns == 11
    assert sample.calls == 17
    assert sample.run_id == sample.id
    assert sample.session_id == f"session-{sample.id}"
    assert launches == list(retained.samples)
