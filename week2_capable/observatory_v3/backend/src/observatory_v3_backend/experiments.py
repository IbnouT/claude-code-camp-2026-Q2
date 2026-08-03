"""Deterministic experiment validation, forking, and queue planning."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from .contracts import (
    ExperimentArmDefinition,
    ExperimentDefinition,
    ExperimentFeature,
    ExperimentValidation,
)
from .experiment_catalog import experiment_scenarios


def validate_definition(
    definition: ExperimentDefinition,
    registry: tuple[ExperimentFeature, ...],
    *,
    execution_available: bool,
    local_spend_cap: float,
) -> ExperimentValidation:
    """Validate comparability and local policy without starting execution."""

    features = {feature.id: feature for feature in registry}
    issues: list[str] = []
    if not definition.title.strip():
        issues.append("A title is required.")
    if not definition.objective.strip():
        issues.append("A plain-language objective is required.")
    if not definition.success_predicate.strip():
        issues.append("An independently verified predicate is required.")
    if not definition.starting_state.strip():
        issues.append("A starting state is required.")
    if len(definition.arms) < 2:
        issues.append("A controlled experiment needs at least two arms.")
    if len({arm.id for arm in definition.arms}) != len(definition.arms):
        issues.append("Arm identifiers must be unique.")
    if len({tuple(sorted(arm.values.items())) for arm in definition.arms}) < 2:
        issues.append("At least one registered field must differ between arms.")
    for arm in definition.arms:
        unknown = sorted(set(arm.values) - set(features))
        missing = sorted(set(features) - set(arm.values))
        if unknown:
            issues.append(
                f"Arm {arm.id} contains unregistered fields: {', '.join(unknown)}."
            )
        if missing:
            issues.append(
                f"Arm {arm.id} does not resolve registered fields: "
                f"{', '.join(missing)}."
            )
        for feature_id, value in arm.values.items():
            feature = features.get(feature_id)
            if feature is not None:
                issue = _value_issue(feature, value)
                if issue:
                    issues.append(f"Arm {arm.id}, {feature.label}: {issue}")
            if (
                feature_id == "policy.max_iterations"
                and feature is not None
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value > definition.stop.max_iterations_per_sample
            ):
                issues.append(
                    f"Arm {arm.id}, {feature.label}: exceeds the definition "
                    "iteration stop."
                )
            if (
                execution_available
                and feature is not None
                and not feature.execution_supported
                and value != feature.default
            ):
                issues.append(
                    f"Arm {arm.id}, {feature.label}: the installed runner "
                    "cannot vary this field with the installed runner."
                )
    scenario = next(
        (
            candidate
            for candidate in experiment_scenarios()
            if candidate.id == definition.journey
        ),
        None,
    )
    if scenario is None:
        issues.append(f"Journey {definition.journey} is not in the scenario registry.")
    elif execution_available and not scenario.execution_supported:
        issues.append(
            f"Journey {definition.journey} is not wired to the installed runner."
        )
    if scenario is not None and definition.reset_identity != scenario.reset_identity:
        issues.append(
            "The definition reset identity does not match the scenario registry."
        )
    if definition.repetitions_per_arm < 1:
        issues.append("Every arm needs at least one repetition.")
    if not 1 <= definition.concurrency <= 4:
        issues.append("Concurrency must be between one and four.")
    if (
        not math.isfinite(definition.per_sample_spend_ceiling_usd)
        or definition.per_sample_spend_ceiling_usd <= 0
    ):
        issues.append("The per-sample spend ceiling must be positive.")
    calculated = (
        len(definition.arms)
        * definition.repetitions_per_arm
        * definition.per_sample_spend_ceiling_usd
    )
    if abs(calculated - definition.effective_max_spend_usd) > 0.000001:
        issues.append(
            "Effective maximum spend does not match arms x repetitions x "
            "per-sample ceiling."
        )
    if not math.isfinite(calculated):
        issues.append("Calculated maximum spend must be finite.")
    elif calculated > definition.stop.max_total_cost_usd:
        issues.append("Calculated maximum spend exceeds the definition cap.")
    if definition.stop.success_target > (
        len(definition.arms) * definition.repetitions_per_arm
    ):
        issues.append("Success target exceeds the planned sample count.")
    if definition.stop.success_target < 1:
        issues.append("Success target must be positive.")
    if definition.stop.max_iterations_per_sample < 1:
        issues.append("The iteration stop must be positive.")
    if definition.stop.max_wall_seconds_per_sample < 1:
        issues.append("The wall-time stop must be positive.")
    if (
        not math.isfinite(definition.stop.max_total_cost_usd)
        or definition.stop.max_total_cost_usd <= 0
    ):
        issues.append("The total-cost stop must be positive.")
    if not definition.stop.verified_predicate_required:
        issues.append("Agent claims cannot replace the verified predicate.")
    if not definition.stop.operator_stop_enabled:
        issues.append("Operator stop must remain available during execution.")
    if local_spend_cap <= 0 or calculated > local_spend_cap:
        issues.append("Calculated maximum spend exceeds local execution policy.")
    reset_identity = definition.reset_identity.strip()
    if not reset_identity:
        issues.append("A verified reset identity is required.")

    comparable = not any(
        marker in issue
        for issue in issues
        for marker in (
            "unregistered",
            "reset identity",
            "at least two arms",
            "Arm identifiers",
        )
    )
    return ExperimentValidation(
        valid=not issues,
        comparable=comparable,
        execution_available=execution_available,
        issues=tuple(issues),
        checks=(
            "Objective and independent success predicate are explicit.",
            "Starting state and reset identity are versioned.",
            "Every effective field belongs to the typed registry.",
            "Arm identifiers and sample ordinals are deterministic.",
            "Six stop criteria bound execution.",
            "Maximum spend is calculated before confirmation.",
        ),
    )


def fork_one_variable(
    definition: ExperimentDefinition,
    *,
    arm_id: str,
    feature_id: str,
    value: bool | int | float | str,
    registry: tuple[ExperimentFeature, ...],
) -> ExperimentDefinition:
    """Return a new immutable definition changing exactly one arm value."""

    feature = next(
        (candidate for candidate in registry if candidate.id == feature_id),
        None,
    )
    if feature is None:
        raise ValueError(f"unknown registered feature {feature_id!r}")
    issue = _value_issue(feature, value)
    if issue:
        raise ValueError(issue)
    found = False
    arms: list[ExperimentArmDefinition] = []
    for arm in definition.arms:
        if arm.id != arm_id:
            arms.append(arm)
            continue
        found = True
        values = dict(arm.values)
        values[feature_id] = value
        arms.append(arm.model_copy(update={"values": values}))
    if not found:
        raise ValueError(f"unknown arm {arm_id!r}")
    changed = f"{arm_id}:{feature_id}"
    digest = hashlib.sha256(
        f"{definition.id}:{definition.version + 1}:{changed}:{value!r}".encode()
    ).hexdigest()[:10]
    return definition.model_copy(
        update={
            "id": f"{definition.id}-fork-{digest}",
            "version": definition.version + 1,
            "arms": tuple(arms),
            "source": "executable_definition",
            "parent_definition_id": definition.id,
            "changed_feature": changed,
        }
    )


def sample_queue(definition: ExperimentDefinition) -> tuple[str, ...]:
    """Return stable sample identities in deterministic interleaved order."""

    return tuple(
        _sample_id(definition.id, arm.id, ordinal)
        for ordinal in range(1, definition.repetitions_per_arm + 1)
        for arm in definition.arms
    )


def remaining_queue(
    definition: ExperimentDefinition,
    completed: set[str],
) -> tuple[str, ...]:
    """Resume without renumbering or repeating completed samples."""

    return tuple(
        sample_id
        for sample_id in sample_queue(definition)
        if sample_id not in completed
    )


def _sample_id(definition_id: str, arm_id: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{definition_id}:{arm_id}:{ordinal}".encode()).hexdigest()[
        :12
    ]
    return f"{arm_id}-{ordinal:03d}-{digest}"


def _value_issue(feature: ExperimentFeature, value: Any) -> str | None:
    if feature.kind == "boolean" and not isinstance(value, bool):
        return "must be a boolean"
    if feature.kind == "integer" and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        return "must be an integer"
    if feature.kind == "number" and (
        not isinstance(value, int | float) or isinstance(value, bool)
    ):
        return "must be a number"
    if feature.kind in {"enum", "text"} and not isinstance(value, str):
        return "must be text"
    if feature.kind == "enum" and value not in feature.options:
        return f"must be one of {', '.join(feature.options)}"
    if feature.kind == "text" and isinstance(value, str) and not value.strip():
        return "must not be empty"
    if (
        feature.kind in {"integer", "number"}
        and isinstance(value, int | float)
        and not isinstance(value, bool)
    ):
        if not math.isfinite(float(value)):
            return "must be finite"
        if feature.minimum is not None and value < feature.minimum:
            return f"must be at least {feature.minimum:g}"
        if feature.maximum is not None and value > feature.maximum:
            return f"must be at most {feature.maximum:g}"
    return None
