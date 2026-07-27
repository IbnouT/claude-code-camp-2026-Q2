"""Per-class cost, and the difference between free, unknown, and partly known.

Rates are data per class, never a multiplier on the input rate: providers price
caching on genuinely different models, so a multiplier would encode one of them.
"""

import unittest

from boukensha.pricing import Cost, cost_of, rates_for, savings
from boukensha.usage import Usage

# Anthropic haiku-4-5 rates, verified from the provider's pricing page.
RATES = {"input": 1.00, "output": 5.00, "cache_read": 0.10,
         "cache_write_5m": 1.25, "cache_write_1h": 2.00}


class TestPerClassCost(unittest.TestCase):
    def test_each_class_is_charged_at_its_own_rate(self):
        cost = cost_of(Usage(fresh_input=1_000_000), RATES)
        self.assertAlmostEqual(1.00, cost.total)
        cost = cost_of(Usage(cache_read=1_000_000), RATES)
        self.assertAlmostEqual(0.10, cost.total)
        cost = cost_of(Usage(cache_write=1_000_000), RATES)
        self.assertAlmostEqual(1.25, cost.total)
        cost = cost_of(Usage(output=1_000_000), RATES)
        self.assertAlmostEqual(5.00, cost.total)

    def test_caching_makes_the_same_prompt_cheaper(self):
        cold = cost_of(Usage(fresh_input=1000, output=20), RATES)
        warm = cost_of(Usage(fresh_input=100, cache_read=900, output=20), RATES)
        self.assertLess(warm.total, cold.total)
        self.assertAlmostEqual(0.00081, savings(cold, warm))

    def test_the_breakdown_names_what_was_charged(self):
        cost = cost_of(Usage(fresh_input=100, cache_read=900, output=20), RATES)
        self.assertEqual({"fresh_input", "cache_read", "output"},
                         set(cost.breakdown))


class TestUnknownIsNotFree(unittest.TestCase):
    def test_no_rates_reports_unavailable(self):
        cost = cost_of(Usage(fresh_input=1000), None)
        self.assertIsNone(cost.total)
        self.assertFalse(cost.available)
        self.assertEqual("cost unavailable", cost.render())

    def test_an_explicit_zero_is_a_known_zero(self):
        cost = cost_of(Usage(fresh_input=1000, output=20),
                       {"input": 0.0, "output": 0.0, "cache_read": 0.0})
        self.assertEqual(0.0, cost.total)
        self.assertTrue(cost.available)
        self.assertEqual("$0.0000", cost.render())

    def test_a_null_input_rate_counts_as_no_rates(self):
        # This is how the catalog records a hosted model with no published price:
        # unknown, which must not read as free.
        self.assertIsNone(rates_for("m", {"m": {"cost_per_million":
                                                {"input": None, "output": None}}}))

    def test_savings_is_unavailable_when_either_side_is(self):
        self.assertIsNone(savings(cost_of(Usage(fresh_input=1), None),
                                  cost_of(Usage(fresh_input=1), RATES)))


class TestPartialRateTables(unittest.TestCase):
    def test_an_unpriced_class_is_named_not_silently_free(self):
        # A table without a cache_read rate must not price 900 cached tokens at
        # zero and report a total that looks complete.
        cost = cost_of(Usage(fresh_input=100, cache_read=900, output=10),
                       {"input": 1.00, "output": 5.00})
        self.assertIn("cache_read", cost.unpriced)
        self.assertNotIn("cache_read", cost.breakdown)


class TestCatalogLookup(unittest.TestCase):
    def test_rates_come_from_the_catalog_entry(self):
        catalog = {"m": {"cost_per_million": {"input": 2.0, "output": 4.0}}}
        self.assertEqual({"input": 2.0, "output": 4.0}, rates_for("m", catalog))

    def test_an_absent_model_has_no_rates(self):
        self.assertIsNone(rates_for("nope", {}))
        self.assertIsNone(rates_for(None, {}))
