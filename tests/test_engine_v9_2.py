"""V9.2 H1 decision tests."""
import unittest
import pandas as pd
import engine_v9_2 as engine


def _frame(closes):
    return pd.DataFrame({"open": closes, "high": [x + 1 for x in closes], "low": [x - 1 for x in closes], "close": closes, "volume": [1.0] * len(closes)})


def _bullish_structure():
    closes=[]
    for i in range(13): closes.extend([100 + i*4, 98 + i*4, 102 + i*4, 100 + i*4])
    return closes[:51]


def _bearish_structure():
    closes=[]
    for i in range(13): closes.extend([150 - i*4, 152 - i*4, 148 - i*4, 150 - i*4])
    return closes[:51]


class TestH1Decision(unittest.TestCase):
    def test_h1_buy_requires_structure_and_ema_alignment(self):
        result = engine._h1_decision(_frame(_bullish_structure()))
        self.assertEqual(result["bias"], "BUY")
        self.assertEqual(result["ema_context"], "BUY")
        self.assertEqual(result["decision"], "BUY")
        self.assertEqual(result["volatility_state"], "NORMAL")

    def test_h1_neutral_when_structure_and_ema_conflict(self):
        closes = _bearish_structure() + [150]
        result = engine._h1_decision(_frame(closes))
        self.assertEqual(result["bias"], "SELL")
        self.assertEqual(result["ema_context"], "BUY")
        self.assertEqual(result["decision"], "NEUTRAL")

    def test_h1_neutral_when_volatility_is_extreme(self):
        frame = _frame(_bullish_structure())
        frame.loc[len(frame) - 1, "high"] = 200
        frame.loc[len(frame) - 1, "low"] = 50
        result = engine._h1_decision(frame)
        self.assertEqual(result["volatility_state"], "EXTREME")
        self.assertEqual(result["decision"], "NEUTRAL")


if __name__ == "__main__":
    unittest.main()
