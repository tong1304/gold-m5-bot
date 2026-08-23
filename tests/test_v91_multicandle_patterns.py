import unittest
import pandas as pd

import engine_v9_1 as engine


class TestV91MultiCandlePatterns(unittest.TestCase):
    def _frame(self, rows):
        return pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close"])

    def test_breakout_retest_uses_multiple_recent_candles(self):
        rows = [
            ("2026-01-01 00:00", 100, 101, 99, 100),
            ("2026-01-01 00:05", 100, 101.2, 99.5, 100.5),
            ("2026-01-01 00:10", 100.5, 101.1, 99.8, 100.2),
            ("2026-01-01 00:15", 100.2, 102.4, 100.0, 102.1),
            ("2026-01-01 00:20", 102.1, 102.3, 101.0, 101.8),
            ("2026-01-01 00:25", 101.8, 103.0, 101.7, 102.8),
        ]
        pattern = engine._m5_pattern_v91(self._frame(rows), "BUY")
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern["name"], "BULLISH_BREAKOUT_RETEST")
        self.assertEqual(pattern["direction"], "BUY")
        self.assertEqual(pattern["quality"], "CLEAR")

    def test_double_bottom_requires_recent_structure_and_break_confirmation(self):
        rows = [
            ("2026-01-01 00:00", 105, 106, 103, 104),
            ("2026-01-01 00:05", 104, 104.5, 100, 101),
            ("2026-01-01 00:10", 101, 103, 100.5, 102),
            ("2026-01-01 00:15", 102, 106, 101.5, 105),
            ("2026-01-01 00:20", 105, 105.5, 100.5, 101.5),
            ("2026-01-01 00:25", 101.5, 103.0, 101.0, 102.5),
            ("2026-01-01 00:30", 102.5, 107.0, 102.2, 106.5),
        ]
        pattern = engine._m5_pattern_v91(self._frame(rows), "BUY")
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern["name"], "DOUBLE_BOTTOM_BREAKOUT")
        self.assertEqual(pattern["direction"], "BUY")


if __name__ == "__main__":
    unittest.main()
