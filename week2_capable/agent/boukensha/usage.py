"""Usage: four token classes, and the four questions they answer.

A cached prompt still sends the same tokens, it just pays a different price for
them, so one number cannot describe a call. This module keeps the classes apart
and derives each metric from the classes rather than from another metric.

    fresh input    tokens the provider processed at the full input rate
    cache read     tokens served from a cache, billed at a reduced rate
    cache write    tokens stored into a cache, billed at a premium
    output         tokens the model generated

Four metrics, none derived from another:

    volume processed    every input class plus output. Unchanged by caching,
                        because the same tokens are still processed and only
                        their price moves. This is what a work ceiling measures.
    window occupancy    the whole prompt, fresh plus cache read plus cache write.
                        Cached tokens still occupy the window.
    billed cost         each class at its own rate, computed in
                        :mod:`boukensha.pricing`.
    amplification       volume processed against genuinely unique tokens, so a
                        session that re-sends one prompt fifty times reads as
                        fifty to one rather than as a large bill with no cause.

Framework-free, so every provider's usage shape is normalized here once and
nothing downstream re-derives it.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Provider key families per class, first present wins. Anthropic and the OpenAI
#: Responses API name these directly; the others are normalized onto them.
_FRESH_KEYS = ("input_tokens", "prompt_tokens", "promptTokenCount",
               "prompt_eval_count")
_OUTPUT_KEYS = ("output_tokens", "completion_tokens", "candidatesTokenCount",
                "eval_count")
_CACHE_READ_KEYS = ("cache_read_input_tokens", "cached_tokens",
                    "cachedContentTokenCount", "cache_read_tokens")
_CACHE_WRITE_KEYS = ("cache_creation_input_tokens", "cache_write_tokens")


#: Prompt-total keys that INCLUDE their cached tokens. Anthropic's
#: ``input_tokens`` excludes them, OpenAI's ``prompt_tokens`` and Gemini's
#: ``promptTokenCount`` include them, so the cached portion is subtracted for
#: those two or fresh input is double counted and occupancy is inflated.
_INCLUSIVE_PROMPT_KEYS = frozenset({"prompt_tokens", "promptTokenCount"})


def _first(mapping, keys):
    """The first present key's int value, with the key that supplied it."""
    for key in keys:
        if key in mapping and mapping[key] is not None:
            try:
                return int(mapping[key]), key
            except (TypeError, ValueError):
                continue
    return None, None


def _nested(response: dict) -> list[dict]:
    """Every mapping a provider might hide usage in, outermost first."""
    out = [response]
    for key in ("usage", "usageMetadata", "usage_metadata"):
        block = response.get(key)
        if isinstance(block, dict):
            out.append(block)
            # OpenAI nests cached_tokens under prompt_tokens_details.
            for inner in ("prompt_tokens_details", "input_tokens_details",
                          "cache_creation"):
                nested = block.get(inner)
                if isinstance(nested, dict):
                    out.append(nested)
    return out


@dataclass(frozen=True)
class Usage:
    """One call's token counts, split by how each class is billed."""

    fresh_input: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0

    @property
    def prompt_tokens(self) -> int:
        """The whole prompt: what occupies the context window.

        Cached tokens are still in the window. Reading occupancy from fresh input
        alone makes a cached session look nearly empty, so compaction would stop
        firing and history would grow until the provider rejects it.
        """
        return self.fresh_input + self.cache_read + self.cache_write

    @property
    def volume(self) -> int:
        """Work processed: every input class plus output.

        Enabling caching does not move this, which is what makes a ceiling
        measured in volume keep its meaning when caching is turned on.
        """
        return self.prompt_tokens + self.output

    @property
    def cached(self) -> bool:
        return bool(self.cache_read or self.cache_write)

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            fresh_input=self.fresh_input + other.fresh_input,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
            output=self.output + other.output,
        )

    def as_dict(self) -> dict[str, int]:
        return {"fresh_input": self.fresh_input, "cache_read": self.cache_read,
                "cache_write": self.cache_write, "output": self.output}

    def __str__(self) -> str:
        return (f"<Usage fresh={self.fresh_input} cache_read={self.cache_read} "
                f"cache_write={self.cache_write} out={self.output}>")

    __repr__ = __str__


def normalize(response: dict) -> Usage:
    """Read any provider's reply into a :class:`Usage`.

    Every provider reports the same four ideas under different names, and some
    nest them. A missing class is zero, never an error: a provider that does not
    cache simply reports no cache tokens.
    """
    if not isinstance(response, dict):
        return Usage()
    blocks = _nested(response)

    def pick(keys):
        for block in blocks:
            value, key = _first(block, keys)
            if value is not None:
                return value, key
        return 0, None

    fresh, fresh_key = pick(_FRESH_KEYS)
    cache_read, _ = pick(_CACHE_READ_KEYS)
    cache_write, _ = pick(_CACHE_WRITE_KEYS)
    output, _ = pick(_OUTPUT_KEYS)

    # Normalize the prompt total to mean fresh input only, whichever convention
    # the provider used, so one Usage means the same thing everywhere.
    if cache_read and fresh_key in _INCLUSIVE_PROMPT_KEYS:
        fresh = max(0, fresh - cache_read)

    return Usage(fresh_input=fresh, cache_read=cache_read,
                 cache_write=cache_write, output=output)


def amplification(volume: int, unique: int) -> float | None:
    """Volume processed per genuinely unique token.

    ``None`` when nothing unique was sent, which is undefined rather than zero.
    A ratio near one means the session barely repeats itself. A large ratio means
    the same tokens are being re-sent, which is what caching makes cheap and a
    smaller prompt makes unnecessary.
    """
    if unique <= 0:
        return None
    return round(volume / unique, 1)
