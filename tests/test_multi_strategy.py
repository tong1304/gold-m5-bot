import unittest
import numpy as np
import pandas as pd
import strategy_engine as se


def candles(n=140, start=100.0, drift=0.08):
    close = start + np.arange(n) * drift + np.sin(np.arange(n) / 3.0) * 0.15
    open_ = close - 0.03
    high = np.maximum(open_, close) + 0.08
    low = np.minimum(open_, close) - 0.08
    return pd.DataFrame({"open":open_,"high":high,"low":low,"close":close,"volume":np.ones(n)})


class MultiStrategyTests(unittest.TestCase):
    def test_strategy_pools_are_asset_specific(self):
        self.assertEqual(len(se.BTC_STRATEGIES), 5)
        self.assertEqual(len(se.GOLD_STRATEGIES), 6)
        self.assertNotIn("SR_REVERSAL", se.BTC_STRATEGIES)
        self.assertIn("LIQUIDITY_SWEEP", se.GOLD_STRATEGIES)

    def test_regime_is_not_selected_from_only_three_candles(self):
        m15 = candles(120, drift=0.12)
        m5 = candles(120, drift=0.03)
        result = se._regime(m15, m5)
        self.assertIn(result["name"], {"TREND_UP", "TREND_DOWN", "BREAKOUT", "VOLATILITY_EXPANSION", "RANGE", "NEUTRAL"})
        self.assertIn("m15_close", result)

    def test_analysis_reports_required_windows(self):
        m15 = candles(120, drift=0.12)
        m5 = candles(120, drift=0.03)
        h1 = candles(80, drift=0.25)
        result = se.analyze(m5, m15, h1, "BTC/USDT")
        self.assertIn("analysis_window", result)
        self.assertEqual(result["analysis_window"]["m15_context_bars"], 100)
        self.assertEqual(result["analysis_window"]["m5_structure_bars"], 50)
        self.assertEqual(result["analysis_window"]["m5_setup_bars"], 20)
        self.assertEqual(result["analysis_window"]["m5_trigger_bars"], 3)

    def test_neutral_regime_does_not_force_trade(self):
        flat = candles(140, drift=0.0)
        result = se.analyze(flat, flat, flat, "GOLD")
        self.assertEqual(result["signal"], "NO_TRADE")
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
