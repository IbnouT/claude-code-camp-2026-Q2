"""Pricing: token classes to money, in one place.

Each class carries its own rate as data in the model catalog, never a multiplier
applied to the input rate. A multiplier would encode one provider's economics:
Anthropic prices two cache lifetimes differently, OpenAI discounts cached input,
and Gemini's explicit cache also bills storage by time. Rates as data describe all
three without the code knowing which is which.

Cost is computed once, here, where the model, the usage, and the rates are all in
hand, and logged as a fact. Nothing downstream recomputes it, so a viewer renders
what was charged rather than re-deriving a second, disagreeing answer.

Unknown and zero are different facts and are kept apart. A local model is priced
at an explicit zero, so its cost is a known zero. A model with no rates returns
``None``, which reports as unavailable. Reporting an unpriced model as $0.00 would
claim it was free.
"""

from __future__ import annotations

from dataclasses import dataclass

from .usage import Usage

#: Which catalog rate pays for which usage class. ``cache_write`` maps to the
#: 5-minute rate: it is the default lifetime, and the 1-hour rate is carried in
#: the catalog for a caller that opts into the longer cache.
_CLASS_RATES = (
    ("fresh_input", "input"),
    ("cache_read", "cache_read"),
    ("cache_write", "cache_write_5m"),
    ("output", "output"),
)


@dataclass(frozen=True)
class Cost:
    """What one call cost, per class and in total.

    ``total`` is ``None`` when the model has no rates. That is unavailable, not
    free, and every consumer has to tell the two apart.
    """

    total: float | None
    breakdown: dict[str, float]
    unpriced: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.total is not None

    def render(self) -> str:
        """Money for a person to read, or an honest absence."""
        if self.total is None:
            return "cost unavailable"
        return f"${self.total:.4f}"

    def __str__(self) -> str:
        return f"<Cost {self.render()} classes={len(self.breakdown)}>"

    __repr__ = __str__


def rates_for(model: str | None, catalog) -> dict[str, float] | None:
    """The per-million rates for a model, or ``None`` when it has none.

    ``catalog`` is any mapping of model name to entry, or an object exposing
    ``cost_per_million(model)``. A rate table present but with a null input rate
    counts as no rates: that is how the catalog records a model whose price is
    genuinely unknown, such as a hosted model with no published figure.
    """
    if not model:
        return None
    getter = getattr(catalog, "cost_per_million", None)
    if callable(getter):
        table = getter(model)
    else:
        entry = (catalog or {}).get(model) or {}
        table = entry.get("cost_per_million") if isinstance(entry, dict) else None
    if not isinstance(table, dict):
        return None
    if table.get("input") is None:
        return None
    return {k: v for k, v in table.items() if v is not None}


def cost_of(usage: Usage, rates: dict[str, float] | None) -> Cost:
    """Price one call's usage, class by class.

    A class the model has no rate for is named in ``unpriced`` rather than
    silently costed at zero, so a partial rate table cannot quietly under-report.
    Charging happens per million tokens.
    """
    if not rates:
        return Cost(total=None, breakdown={})
    breakdown: dict[str, float] = {}
    unpriced: list[str] = []
    for field, rate_key in _CLASS_RATES:
        count = getattr(usage, field, 0) or 0
        if not count:
            continue
        rate = rates.get(rate_key)
        if rate is None:
            unpriced.append(field)
            continue
        breakdown[field] = count * float(rate) / 1_000_000
    total = round(sum(breakdown.values()), 8)
    return Cost(total=total, breakdown=breakdown, unpriced=tuple(unpriced))


def savings(cold: Cost, warm: Cost) -> float | None:
    """What caching saved between two comparable calls, or ``None`` if unpriced."""
    if cold.total is None or warm.total is None:
        return None
    return round(cold.total - warm.total, 8)
