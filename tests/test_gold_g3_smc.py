import unittest
import numpy as np
import pandas as pd

from v11.strategies.gold.g3_smc import evaluate


def smc_fixture():
    n = 60
    idx = np.arange(n)
    close = np.full(n, 100.0)
    open_ = np.full(n, 100.0)
    high = np.full(n, 100.4)
    low = np.full(n, 99.6)

    # Two nearby swing lows create an EQL liquidity pool around 98.0.
    for i, value in ((42, 98.0), (46, 98.05)):
        open_[i] = close[i] = 98.8
        high[i] = 99.0
        low[i] = value

    # Last protected swing high before the sweep.
    open_[50] = 99.7
    close[50] = 99.8
    high[50] = 100.0
    low[50] = 99.5

    # Bearish order-block candle immediately before displacement.
    open_[51] = 99.8
    close[51] = 99.1
    high[51] = 99.9
    low[51] = 98.9

    # Liquidity sweep: pierces EQL, rejects and closes back above it.
    open_[52] = 98.7
    close[52] = 98.6
    high[52] = 99.0
    low[52] = 97.4

    # Bullish CHoCH + momentum. Low is above candle 51 high -> bullish FVG.
    open_[53] = 99.0
    close[53] = 101.4
    high[53] = 101.6
    low[53] = 100.4

    # Keep the latest closed candle after the CHoCH so the engine can find the setup.
    open_[54] = 101.2
    close[54] = 101.5
    high[54] = 101.8
    low[54] = 101.0

    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.ones(n),
        "datetime": pd.date_range("2026-08-24", periods=n, freq="5min", tz="UTC"),
    })


class GoldG3SMCTests(unittest.TestCase):
    def test_bullish_liquidity_sweep_requires_choch_and_fvg(self):
        result = evaluate(smc_fixture(), "BUY", {
            "h1_bias": "BUY",
            "m15": {"direction": "BUY"},
        })
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.strategy, "G3_LIQUIDITY_SWEEP_CHOCH")
        self.assertEqual(result.direction, "BUY")
        self.assertTrue(result.evidence["sweep_confirmed"])
        self.assertTrue(result.evidence["choch_confirmed"])
        self.assertTrue(result.evidence["fvg_confirmed"])
        self.assertIn("entry", result.evidence)
        self.assertIn("sl", result.evidence)

    def test_no_fvg_is_a_hard_rejection(self):
        frame = smc_fixture()
        frame.loc[53, "low"] = 99.7
        result = evaluate(frame, "BUY", {
            "h1_bias": "BUY",
            "m15": {"direction": "BUY"},
        })
        self.assertEqual(result.status, "FAIL")
        self.assertIn("NO_FVG_AFTER_CHOCH", result.reasons)

    def test_countertrend_without_htf_poi_is_rejected(self):
        result = evaluate(smc_fixture(), "BUY", {
            "h1_bias": "SELL",
            "m15": {"direction": "SELL"},
        })
        self.assertEqual(result.status, "FAIL")
        self.assertIn("HTF_ALIGNMENT_FAILED", result.reasons)


if __name__ == "__main__":
    unittest.main()
