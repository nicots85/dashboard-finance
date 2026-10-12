"""Toda la historia, tramo reciente y regla limitada de Solana son distintos."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

from src.data.backup import ROOT
from src.indices_math import pair_analysis
from src.pilot_math import cointegration_parameters


def series(count):
    rng = np.random.default_rng(14)
    x = np.cumsum(rng.normal(0, .01, count)) + 5
    y = 1.5 * x + rng.normal(0, .01, count)
    return pd.Series(np.exp(y)), pd.Series(np.exp(x))


YES = {"p_yx": .01, "p_xy": .02, "johansen_rank": 1}
NO = {"p_yx": .5, "p_xy": .6, "johansen_rank": 0}


class BlockStatisticsTests(unittest.TestCase):
    def config(self):
        pilot = yaml.safe_load((ROOT / "config/sections.yaml").read_text())["cripto"]
        pilot["cointegration"] = {**pilot["cointegration"], "primary_window": 50, "contrast_window": 100,
                                  "short_spread_window": 25, "rolling_step": 50}
        # Esta suite aísla estadísticas y criterio reciente; la significación
        # binomial se comprueba independientemente en test_binomial.py.
        pilot["cointegration"].pop("binomial_gate", None)
        return pilot

    def test_all_blocks_percent_does_not_replace_recent_state(self):
        cfg = self.config()["cointegration"]
        with patch("src.indices_math._pair_test", side_effect=[NO] * 5 + [YES] * 2 + [NO, NO]):
            result = pair_analysis(*series(350), cfg)
        self.assertEqual(result["state"], "sin relación")
        self.assertEqual(result["confirmed_blocks"], 0)
        total = result["all_block_statistics"]
        self.assertEqual((total["available"], total["evaluated"], total["confirmed"]), (7, 7, 2))
        self.assertAlmostEqual(total["confirmation_pct"], 2 / 7 * 100)
        self.assertEqual(result["recent_block_statistics"]["confirmed"], 0)

    def test_invalid_old_block_does_not_fabricate_a_percent(self):
        cfg = self.config()["cointegration"]
        with patch("src.indices_math._pair_test", side_effect=[YES] * 6 + [RuntimeError("bloque inválido"), YES, YES]):
            result = pair_analysis(*series(350), cfg)
        self.assertEqual(result["state"], "estable")
        total = result["all_block_statistics"]
        self.assertEqual((total["available"], total["evaluated"], total["failed"]), (7, 6, 1))
        self.assertIsNone(total["confirmation_pct"])

    def test_solana_four_blocks_is_provisional_and_five_is_normal(self):
        pilot = self.config()
        cfg = cointegration_parameters(pilot, "ETH/USDT", "SOL/USDT", "1D", 249)
        self.assertEqual((cfg["required_blocks"], cfg["stable_blocks"]), (4, 4))
        with patch("src.indices_math._pair_test", return_value=YES):
            result = pair_analysis(*series(249), cfg)
        self.assertEqual(result["state"], "Estable (provisional)")
        self.assertTrue(result["limited_history"])
        cfg = cointegration_parameters(pilot, "ETH/USDT", "SOL/USDT", "1D", 250)
        self.assertEqual(cfg["required_blocks"], 5)
        self.assertFalse(cfg.get("provisional", False))
        with patch("src.indices_math._pair_test", return_value=YES):
            result = pair_analysis(*series(250), cfg)
        self.assertEqual(result["state"], "estable")

    def test_limited_rule_does_not_apply_to_other_pairs_or_three_blocks(self):
        pilot = self.config()
        for y, x, bars in [("BTC/USDT", "ETH/USDT", 249), ("BTC/USDT", "SOL/USDT", 199)]:
            cfg = cointegration_parameters(pilot, y, x, "1D", bars)
            self.assertEqual(cfg["required_blocks"], 5)
            self.assertFalse(cfg.get("provisional", False))
            with patch("src.indices_math._pair_test", return_value=YES):
                self.assertEqual(pair_analysis(*series(bars), cfg)["state"], "no calculable")

    def test_hourly_block_size_is_independent_of_primary_test_window(self):
        pilot = yaml.safe_load((ROOT / "config/sections.yaml").read_text())["cripto"]
        cfg = cointegration_parameters(pilot, "BTC/USDT", "ETH/USDT", "1h", 79936)
        self.assertEqual(cfg["block_size"], 1000)
        self.assertEqual(cfg["primary_window"], 500)
        with patch("src.indices_math._pair_test", return_value=NO), patch(
            "src.indices_math.coint", return_value=(0., .5, None)
        ):
            result = pair_analysis(*series(79936), cfg)
        self.assertEqual(result["all_block_statistics"]["available"], 79)
        self.assertEqual(result["all_block_statistics"]["evaluated"], 79)
        self.assertEqual(result["evaluated_blocks"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
