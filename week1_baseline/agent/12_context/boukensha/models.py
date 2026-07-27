"""Model catalog: context windows and costs as configurable data.

The bundled ``models.yaml`` ships with the package. A ``models.yaml`` in the
user's ``.boukensha`` directory overrides or extends it per model, so a new
model is a configuration edit, never a code change.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

BUNDLED_CATALOG = files("boukensha") / "models.yaml"

#: The ordered thinking-depth axis, low to high. This is both the settable
#: vocabulary and the clamp order, since per-model clamping makes every value
#: safe on every model. "none" is the floor: it turns thinking off where the
#: model supports that and clamps to the model's minimum where it does not.
#: "none" (off) is distinct from leaving the setting unset (use the model's
#: own default, which for most models is to think).
THINKING_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


class ModelCatalog:
    """Per-provider model metadata, bundled data plus a user override."""

    def __init__(self, override_path: Path | None = None) -> None:
        self._table: dict[str, dict[str, Any]] = (
            yaml.safe_load(BUNDLED_CATALOG.read_text()) or {}
        )
        if override_path is not None:
            override_path = Path(override_path)
            if override_path.is_file():
                self._merge(yaml.safe_load(override_path.read_text()) or {})

    def _merge(self, override: dict[str, Any]) -> None:
        for provider, models in override.items():
            self._table.setdefault(provider, {}).update(models or {})

    def info(self, provider: str, model: str) -> dict[str, Any]:
        """The model's catalog entry. An unknown model raises ConfigError."""
        entry = self._table.get(provider, {}).get(model)
        if entry is None:
            known = ", ".join(sorted(self._table.get(provider, {}))) or "none"
            raise ConfigError(
                f"model '{model}' is not in the model catalog for provider "
                f"'{provider}'. Known {provider} models: {known}. Add '{model}' "
                f"to models.yaml in your .boukensha directory "
                f"(context_window, cost_per_million)."
            )
        return entry

    def __str__(self) -> str:
        counts = {p: len(m) for p, m in self._table.items()}
        return f"<ModelCatalog models={counts}>"

    __repr__ = __str__


_default: ModelCatalog | None = None


def default_catalog() -> ModelCatalog:
    """The shared catalog: bundled data plus the user's override, loaded once.

    The override is ``models.yaml`` in the directory ``Config.resolve_dir()``
    names, the same resolution every component uses. Only the path resolution
    is shared; nothing else from the config directory is loaded here.
    """
    global _default
    if _default is None:
        from .config import Config
        _default = ModelCatalog(Config.resolve_dir() / "models.yaml")
    return _default
