"""V9.2 H1 decision tests."""
import unittest
import pandas as pd
import engine_v9_2 as engine


def _frame(closes):
    return pd.DataFrame({"open": closes, "high": [x + 1 for x in closes], "low": [x - 1 for x in closes], "close": closes, "volume": [1.0] * len(closes)})


class TestH1Decision(unittest.TestCase):
    def test_h1_buy_requires_structure_and_ema_alignment(self):
        closes = list(range(100, 151))
        result = engine._h1_decision(_frame(closes))
        self.assertEqual(result["bias"], "BUY")
        self.assertEqual(result["ema_context"], "BUY")
        self.assertEqual(result["decision"], "BUY")
        self.assertEqual(result["volatility_state"], "NORMAL")

    def test_h1_neutral_when_structure_and_ema_conflict(self):
        closes = list(range(150, 100, -1)) + [150]
        result = engine._h1_decision(_frame(closes))
        self.assertEqual(result["bias"], "SELL")
        self.assertEqual(result["ema_context"], "BUY")
        self.assertEqual(result["decision"], "NEUTRAL")

    def test_h1_neutral_when_volatility_is_extreme(self):
        closes = list(range(100, 151))
        frame = _frame(closes)
        frame.loc[len(frame) - 1, "high"] = 200
        frame.loc[len(frame) - 1, "low"] = 50
        result = engine._h1_decision(frame)
        self.assertEqual(result["volatility_state"], "EXTREME")
        self.assertEqual(result["decision"], "NEUTRAL")


if __name__ == "__main__":
    unittest.main()
