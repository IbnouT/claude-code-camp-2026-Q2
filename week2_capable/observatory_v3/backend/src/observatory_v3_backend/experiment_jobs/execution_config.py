"""Installed typed configuration boundary for experiment process execution."""

from __future__ import annotations

import math
from pathlib import Path

import yaml

from ..contracts import ExperimentDefinition, ExperimentFeature


def installed_models(repository_root: Path) -> frozenset[str]:
    """Return model ids from the installed bundled agent catalog."""
    path = repository_root / "week2_capable" / "agent" / "boukensha" / "models.yaml"
    if not path.is_file():
        installed_root = Path(__file__).resolve().parents[6]
        path = installed_root / "week2_capable" / "agent" / "boukensha" / "models.yaml"
    if not path.is_file():
        return frozenset()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise RuntimeError("installed model catalog must be a mapping")
    models = frozenset(
        str(model)
        for provider in loaded.values()
        if isinstance(provider, dict)
        for model in provider
    )
    if not models:
        raise RuntimeError("installed model catalog is empty")
    return models


def validate_effective_config(
    definition: ExperimentDefinition,
    values: dict[str, bool | int | float | str],
    *,
    repository_root: Path,
) -> None:
    """Reject any value that cannot be represented by the installed runner."""
    from ..experiment_catalog import experiment_registry

    registry = {feature.id: feature for feature in experiment_registry()}
    unknown = set(values) - set(registry)
    missing = set(registry) - set(values)
    if unknown:
        raise ValueError(
            f"effective config contains unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise ValueError(f"effective config omits fields: {', '.join(sorted(missing))}")
    for feature_id, feature in registry.items():
        value = values[feature_id]
        issue = _value_issue(feature, value)
        if issue is not None:
            raise ValueError(f"{feature_id} {issue}")
        if not feature.execution_supported and value != feature.default:
            raise ValueError(f"{feature_id} is not executable by the installed runner")
    model = values["model.id"]
    if not isinstance(model, str) or model not in installed_models(repository_root):
        raise ValueError("model.id is not in the installed catalog")
    iterations = values["policy.max_iterations"]
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or not 1 <= iterations <= min(10_000, definition.stop.max_iterations_per_sample)
    ):
        raise ValueError("policy.max_iterations exceeds the typed definition boundary")


def _value_issue(
    feature: ExperimentFeature,
    value: bool | int | float | str,
) -> str | None:
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
