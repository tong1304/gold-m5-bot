import unittest
import pandas as pd
import numpy as np

import engine_v6 as engine


class EngineV6Tests(unittest.TestCase):
    def frame(self, n=80):
        base = np.linspace(100, 120, n)
        return pd.DataFrame({
            "datetime": pd.date_range("2026-08-01", periods=n, freq="5min", tz="UTC"),
            "open": base,
            "high": base + 1,
            "low": base - 1,
            "close": base + 0.5,
            "volume": 1.0,
        })

    def test_sweep_is_causal(self):
        df = self.frame()
        # Current candle sweeps the prior ten-bar low and closes back above it.
        df.loc[79, ["open", "high", "low", "close"]] = [119.5, 121, 100, 120.5]
        sweep = engine._find_sweep(df, 79, "BUY", window=10)
        self.assertIsNotNone(sweep)
        self.assertEqual(sweep["type"], "LIQUIDITY_SWEEP_LOW")

    def test_mss_only_uses_candles_after_sweep(self):
        df = self.frame()
        df.loc[75, ["open", "high", "low", "close"]] = [115, 116, 113, 115.5]
        df.loc[76, ["open", "high", "low", "close"]] = [115.4, 120, 115, 119.5]
        mss = engine._find_mss(df, 75, 79, "BUY", window=8)
        self.assertIsNotNone(mss)
        self.assertEqual(mss["index"], 76)

    def test_trade_levels_reject_rr_below_two(self):
        df = self.frame()
        levels = engine.build_v6_trade_levels(df, 79, "BUY", invalidation=119.0, target=120.0)
        self.assertFalse(levels["valid"])
        self.assertEqual(levels["reason"], "RR_BELOW_2R")

    def test_execution_costs_do_not_reduce_required_rr(self):
        result = engine.validate_trade_levels(100, 99, 102)
        self.assertTrue(result["valid"])
        self.assertGreaterEqual(result["effective_rr"], 2.0)


if __name__ == "__main__":
    unittest.main()
