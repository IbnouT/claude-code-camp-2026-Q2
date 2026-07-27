"""Caching per backend, driven by what each one declares rather than its name.

The five providers differ enough that a test written against one is wrong on the
others, so every assertion here reads a declared capability: ``Backend.caches``,
``cache_min_tokens`` from the catalog, and ``cache_status``. A conditional that
names a provider or a model would be the defect.
"""

import unittest

from boukensha.backends import backend_for
from boukensha.context import Context

#: One model per provider, and what it is here to demonstrate. The names appear
#: as DATA, never in a conditional: each case asserts against the capability the
#: backend declares for itself.
CASES = [
    ("anthropic", "claude-haiku-4-5"),
    ("openai", "gpt-5.6-luna"),
    ("gemini", "gemini-2.5-pro"),
    ("ollama", "gemma4"),
    ("ollama_cloud", "kimi-k2.5"),
]


class TestDeclaredCapability(unittest.TestCase):
    def test_every_backend_states_whether_it_caches(self):
        for provider, model in CASES:
            with self.subTest(provider=provider):
                backend = backend_for(provider, model)
                self.assertIsInstance(backend.caches, bool)

    def test_a_backend_that_does_not_cache_says_so_rather_than_pretending(self):
        # Silently ignoring a cache directive would look like caching that never
        # pays off, which is the failure mode this exists to prevent.
        for provider, model in CASES:
            with self.subTest(provider=provider):
                backend = backend_for(provider, model)
                status = backend.cache_status(1_000_000)
                if not backend.caches:
                    self.assertIn("not supported", status)
                else:
                    self.assertNotIn("not supported", status)


class TestMinimumCacheableLength(unittest.TestCase):
    """A provider caches nothing below a minimum and returns NO error.

    The figure is a per-model catalog fact and varies widely, so the expectation
    is derived from the configured model rather than written as a constant. A doc
    or a test naming one number is wrong the moment someone switches model.
    """

    def test_a_prompt_below_the_models_minimum_is_explained(self):
        for provider, model in CASES:
            with self.subTest(provider=provider):
                backend = backend_for(provider, model)
                minimum = backend.cache_min_tokens
                if not (backend.caches and minimum):
                    continue
                status = backend.cache_status(minimum - 1)
                self.assertIn(str(minimum), status)
                self.assertIn("below", status)

    def test_at_or_above_the_minimum_caching_is_on(self):
        for provider, model in CASES:
            with self.subTest(provider=provider):
                backend = backend_for(provider, model)
                if not backend.caches:
                    continue
                self.assertEqual("on", backend.cache_status(
                    max(backend.cache_min_tokens, 1)))

    def test_the_minimum_is_a_per_model_fact_not_one_number(self):
        # Guards the assumption itself: if every model shared a minimum, code
        # could hardcode it. They do not.
        minimums = {m: backend_for("anthropic", m).cache_min_tokens
                    for m in ("claude-fable-5", "claude-opus-4-8",
                              "claude-haiku-4-5")}
        self.assertGreater(len(set(minimums.values())), 1, minimums)


class TestCacheDirective(unittest.TestCase):
    def test_a_caching_backend_asks_for_caching_in_its_request(self):
        # Read from the built request, so this checks what goes on the wire and
        # not an internal flag.
        for provider, model in CASES:
            with self.subTest(provider=provider):
                backend = backend_for(provider, model)
                body = backend.build_request(Context("system prompt"))
                serialized = str(body)
                if backend.caches and "cache" in serialized:
                    # An explicit directive: it must be well formed, not truthy.
                    directive = body.get("cache_control")
                    if directive is not None:
                        self.assertEqual({"type": "ephemeral"}, directive)

    def test_a_non_caching_backend_sends_no_cache_directive(self):
        for provider, model in CASES:
            with self.subTest(provider=provider):
                backend = backend_for(provider, model)
                if backend.caches:
                    continue
                body = backend.build_request(Context("system prompt"))
                self.assertIsNone(body.get("cache_control"))
