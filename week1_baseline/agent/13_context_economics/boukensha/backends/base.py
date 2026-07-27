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
    from ..pricing import Cost
    from ..context import Context
    from ..message import ParsedResponse
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

    #: Whether this backend can cache a prompt prefix at all. Overridden per
    #: backend: Ollama has no caching, so it says so rather than appearing to
    #: support something it silently ignores.
    caches: ClassVar[bool] = False

    @property
    def cache_min_tokens(self) -> int:
        """Smallest prompt this model can cache, from the catalog.

        Providers refuse to cache a short prompt and return NO error, they simply
        skip it. The figure varies widely between models (512 to 4096 on
        Anthropic alone), so a caller that wants to explain an absent cache hit
        needs the number rather than a guess.
        """
        return int(self._info.get("cache_min_tokens") or 0)

    def cache_status(self, prompt_tokens: int) -> str:
        """Why caching is or is not happening, in words a person can act on.

        Silent non-caching is the failure this exists to prevent: a prompt under
        the model's minimum produces no cache hits and no explanation.
        """
        if not self.caches:
            return "not supported by this provider"
        minimum = self.cache_min_tokens
        if minimum and prompt_tokens < minimum:
            return f"prompt {prompt_tokens} below this model's {minimum} minimum"
        return "on"

    @property
    def rates(self) -> dict[str, float] | None:
        """This model's per-million rates per token class, or None if unpriced.

        A table whose ``input`` is null records a model whose price is genuinely
        unknown, which is not the same as free, so it reads as no rates at all.
        """
        table = self._info.get("cost_per_million") or {}
        if not isinstance(table, dict) or table.get("input") is None:
            return None
        return {k: v for k, v in table.items() if v is not None}

    def cost_of(self, usage) -> "Cost":
        """Price one call's four-class usage at this model's rates.

        Cost is computed here, where the model, the usage, and the rates are all
        in hand, and logged as a fact. Nothing downstream recomputes it, so a
        viewer renders what was charged instead of deriving a second answer.
        """
        from ..pricing import cost_of as _cost_of

        return _cost_of(usage, self.rates)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        """The USD cost of a fresh-input call, kept for callers that have only
        two counts. Prefer :meth:`cost_of`, which prices cached classes too."""
        from ..pricing import cost_of as _cost_of
        from ..usage import Usage

        return _cost_of(Usage(fresh_input=input_tokens, output=output_tokens),
                        self.rates).total

    # -- surface -----------------------------------------------------------

    def build_request(self, context: Context, tools: Sequence[Tool] = (),
                      max_output_tokens: int = 1024,
                      thinking: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def headers(self) -> dict[str, str]:
        raise NotImplementedError

    def url(self) -> str:
        raise NotImplementedError

    def configure_host(self, host: str) -> None:
        """Apply a caller-supplied base URL. A backend with no configurable
        host ignores it, so a caller never has to special-case by provider."""
        return None

    def parse_response(self, response: dict[str, Any]) -> ParsedResponse:
        """Normalize this provider's raw reply to the common typed shape."""
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
