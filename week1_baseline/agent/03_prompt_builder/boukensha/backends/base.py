"""Backend: one uniform surface over the provider wire formats.

Each concrete backend translates the typed conversation blocks to its
provider's request shape. Every provider difference lives inside a backend,
and callers only ever see this interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Sequence

from ..errors import ConfigError
from ..models import THINKING_LEVELS, ModelCatalog, default_catalog

if TYPE_CHECKING:
    from ..context import Context
    from ..tool import Tool


class Backend:
    """Builds provider requests. Concrete backends implement the surface."""

    #: Name used by backend_for.
    provider_name: ClassVar[str] = ""
    #: Environment variable the API key is read from, None when keyless.
    api_key_env: ClassVar[str | None] = None

    def __init__(self, model: str, api_key: str | None = None,
                 catalog: ModelCatalog | None = None) -> None:
        self.model = model
        self.api_key = api_key
        self._info = (catalog or default_catalog()).info(self.provider_name, model)

    # -- model metadata ----------------------------------------------------

    @property
    def context_window(self) -> int:
        return self._info["context_window"]

    @property
    def usage_unit(self) -> str:
        """How usage is billed: tokens, local_compute, or subscription."""
        return self._info.get("usage_unit", "tokens")

    @property
    def usage_level(self) -> str | None:
        """Subscription burn-rate tier, when the catalog states one."""
        return self._info.get("usage_level")

    @property
    def thinking_mode(self) -> str | None:
        """The model's thinking form from the catalog, None when it has none."""
        return self._info.get("thinking")

    @property
    def thinking_levels(self) -> list[str] | None:
        """Level values the model documents, None when the catalog lists none."""
        return self._info.get("thinking_levels")

    @property
    def thinking_default(self) -> str | None:
        """The model's documented default thinking state: off, on, always_on."""
        return self._info.get("thinking_default")

    def _resolve_thinking_level(self, level: str) -> str | None:
        """Clamp a requested level onto what the model supports.

        The requested level is a ceiling: the result is the highest supported
        level at or below it, so a clamp never raises thinking depth or spend
        above what was asked. When no supported level is at or below the
        request, the model's lowest supported level is returned. Models whose
        catalog entry lists no levels pass the request through unchanged, and a
        model with no usable level gets None. How a backend expresses "off" for
        a requested ``none`` is decided in the backend, not here.
        """
        if level not in THINKING_LEVELS:
            raise ConfigError(
                f"unknown thinking level '{level}'; valid: "
                f"{', '.join(THINKING_LEVELS)}"
            )
        levels = self.thinking_levels
        if levels is None:
            return level
        eligible = [l for l in THINKING_LEVELS if l in levels]
        if not eligible:
            return None
        rank = THINKING_LEVELS.index(level)
        at_or_below = [l for l in eligible if THINKING_LEVELS.index(l) <= rank]
        return at_or_below[-1] if at_or_below else eligible[0]

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        """The USD cost at this model's per-million rates.

        None when the model has no per-token price (subscription billing), so
        an unknown cost is never reported as zero.
        """
        rates = self._info.get("cost_per_million") or {}
        if rates.get("input") is None or rates.get("output") is None:
            return None
        return (
            input_tokens * rates["input"] + output_tokens * rates["output"]
        ) / 1_000_000

    # -- surface -----------------------------------------------------------

    def build_request(self, context: Context, tools: Sequence[Tool] = (),
                      max_output_tokens: int = 1024,
                      thinking: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def headers(self) -> dict[str, str]:
        raise NotImplementedError

    def url(self) -> str:
        raise NotImplementedError

    # -- shared helpers ----------------------------------------------------

    @staticmethod
    def _json_schema(tool: Tool) -> dict[str, Any]:
        """The tool's parameters as a JSON Schema object."""
        return {
            "type": "object",
            "properties": dict(tool.parameters),
            "required": tool.required_parameters,
        }

    def __str__(self) -> str:
        return f"<{type(self).__name__} model={self.model}>"

    __repr__ = __str__
