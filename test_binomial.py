"""Significación de bloques: no atribuir evidencia compatible con azar."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scipy.stats import binom
from src.calc.binomial_evidence import minimum_confirmations, binomial_evidence
from src.indices_math import pair_analysis


YES = {"p_yx": .01, "p_xy": .01, "johansen_rank": 1}
NO = {"p_yx": .5, "p_xy": .5, "johansen_rank": 0}


class BinomialTests(unittest.TestCase):
    def test_requested_minima_and_unilateral_tail(self):
        self.assertEqual(minimum_confirmations(6), 2)
        self.assertEqual(minimum_confirmations(13), 3)
        for n in (4, 5, 6, 13, 20, 40, 80):
            k = minimum_confirmations(n)
            self.assertLessEqual(binom.sf(k - 1, n, .05), .05)
            if k > 1:
                self.assertGreater(binom.sf(k - 2, n, .05), .05)
        result = binomial_evidence(1, 13)
        self.assertAlmostEqual(result["expected_by_chance"], .65)
        self.assertFalse(result["significant"])
        self.assertTrue(binomial_evidence(3, 13)["significant"])

    def test_zero_and_invalid_counts_are_not_significant(self):
        self.assertFalse(binomial_evidence(0, 0)["significant"])
        self.assertIsNone(binomial_evidence(0, 0)["minimum_confirmed"])
        with self.assertRaises(ValueError):
            binomial_evidence(3, 2)

    def evaluate(self, confirmed, n, recent_yes=False, primary_yes=False, provisional=False):
        count = n * 50
        rng = np.random.default_rng(14)
        x = np.cumsum(rng.normal(0, .01, count)) + 5
        y = 1.5 * x + rng.normal(0, .02, count)
        cfg = {"primary_window": 50, "block_size": 50, "contrast_window": 100, "short_spread_window": 25,
               "required_blocks": 4 if provisional else 5, "stable_blocks": 4, "p_threshold": .05,
               "johansen_diff_lags": 1, "rolling_step": 50, "include_rolling": False,
               "all_block_statistics": True, "binomial_gate": {"null_probability": .05, "alpha": .05},
               "provisional": provisional}
        tests = ([YES] * confirmed + [NO] * (n - confirmed)) if recent_yes else ([NO] * (n - confirmed) + [YES] * confirmed)
        tests += [YES if primary_yes else NO] * 2
        with patch("src.indices_math._pair_test", side_effect=tests):
            return pair_analysis(pd.Series(np.exp(y)), pd.Series(np.exp(x)), cfg)

    def test_single_confirmation_and_isolated_current_test_do_not_make_intermittent(self):
        result = self.evaluate(1, 6, recent_yes=True, primary_yes=True)
        self.assertEqual(result["state"], "sin relación (compatible con azar)")
        self.assertEqual(result["binomial_evidence"]["minimum_confirmed"], 2)

    def test_significant_history_is_intermittent_without_current_stability(self):
        result = self.evaluate(3, 13)
        self.assertTrue(result["binomial_evidence"]["significant"])
        self.assertEqual(result["state"], "intermitente")
        self.assertEqual(result["confirmed_blocks"], 0)

    def test_stable_and_provisional_keep_strict_previous_conditions(self):
        self.assertEqual(self.evaluate(4, 5, recent_yes=True, primary_yes=True)["state"], "estable")
        self.assertEqual(self.evaluate(4, 4, recent_yes=True, primary_yes=True, provisional=True)["state"], "Estable (provisional)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
