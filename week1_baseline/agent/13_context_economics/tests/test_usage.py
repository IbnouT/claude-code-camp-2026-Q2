"""Four token classes, normalized from whatever shape a provider reports.

The classes are not interchangeable: a cached token is processed like any other
but billed differently, so collapsing them loses the distinction every metric in
this step depends on. These are hermetic unit tests on the wire shapes, taken
from each provider's documented usage fields.
"""

import unittest

from boukensha.usage import Usage, amplification, normalize

# Each provider's documented shape for the SAME logical call: a 1,000-token
# prompt of which 900 were served from cache, and 20 tokens out.
SHAPES = {
    "anthropic": {"usage": {"input_tokens": 100, "cache_read_input_tokens": 900,
                            "cache_creation_input_tokens": 0, "output_tokens": 20}},
    "openai": {"usage": {"prompt_tokens": 1000, "completion_tokens": 20,
                         "prompt_tokens_details": {"cached_tokens": 900}}},
    "gemini": {"usageMetadata": {"promptTokenCount": 1000,
                                 "candidatesTokenCount": 20,
                                 "cachedContentTokenCount": 900}},
}


class TestNormalizeAgreesAcrossProviders(unittest.TestCase):
    def test_the_same_call_reads_the_same_everywhere(self):
        # Anthropic reports a prompt total EXCLUDING cached tokens while OpenAI
        # and Gemini INCLUDE them. Without normalizing that, fresh input is
        # double counted and occupancy is inflated by the cached portion.
        for provider, response in SHAPES.items():
            with self.subTest(provider=provider):
                usage = normalize(response)
                self.assertEqual(100, usage.fresh_input)
                self.assertEqual(900, usage.cache_read)
                self.assertEqual(20, usage.output)
                self.assertEqual(1000, usage.prompt_tokens)

    def test_a_provider_without_caching_reports_no_cache_tokens(self):
        usage = normalize({"prompt_eval_count": 1000, "eval_count": 20})
        self.assertEqual(1000, usage.fresh_input)
        self.assertEqual(0, usage.cache_read)
        self.assertEqual(0, usage.cache_write)
        self.assertFalse(usage.cached)

    def test_a_missing_usage_block_is_zeros_not_an_error(self):
        for response in ({}, {"usage": {}}, None, "not a dict"):
            with self.subTest(response=response):
                self.assertEqual(Usage(), normalize(response))

    def test_a_cache_write_is_its_own_class(self):
        usage = normalize({"usage": {"input_tokens": 50,
                                     "cache_creation_input_tokens": 4000,
                                     "output_tokens": 10}})
        self.assertEqual(4000, usage.cache_write)
        self.assertEqual(4050, usage.prompt_tokens)


class TestOccupancyCountsCachedTokens(unittest.TestCase):
    """The precondition the whole step rests on.

    A provider bills cached tokens less, it does not stop sending them, so they
    still fill the window. Reading occupancy from fresh input alone makes a cached
    session look nearly empty and compaction never fires again.
    """

    def test_prompt_tokens_is_every_input_class(self):
        usage = Usage(fresh_input=500, cache_read=9000, cache_write=100, output=30)
        self.assertEqual(9600, usage.prompt_tokens)

    def test_fresh_input_alone_would_understate_occupancy(self):
        usage = Usage(fresh_input=500, cache_read=9000, output=30)
        self.assertEqual(9500, usage.prompt_tokens)
        self.assertNotEqual(usage.fresh_input, usage.prompt_tokens)


class TestVolumeSurvivesCaching(unittest.TestCase):
    """Why the corrected token ceiling keeps its meaning when caching is on."""

    def test_the_same_work_reports_the_same_volume_cached_or_not(self):
        cold = Usage(fresh_input=1000, output=20)
        warm = Usage(fresh_input=100, cache_read=900, output=20)
        self.assertEqual(cold.volume, warm.volume)

    def test_volume_includes_output(self):
        self.assertEqual(1020, Usage(fresh_input=1000, output=20).volume)


class TestAmplification(unittest.TestCase):
    def test_repetition_shows_as_a_ratio(self):
        self.assertEqual(10.4, amplification(73043, 7000))

    def test_no_repetition_is_about_one(self):
        self.assertEqual(1.0, amplification(1000, 1000))

    def test_undefined_rather_than_zero_when_nothing_is_unique(self):
        self.assertIsNone(amplification(500, 0))


class TestUsageAdds(unittest.TestCase):
    def test_summing_keeps_the_classes_apart(self):
        total = Usage(fresh_input=10, cache_read=5) + Usage(fresh_input=1, output=2)
        self.assertEqual(Usage(fresh_input=11, cache_read=5, output=2), total)
