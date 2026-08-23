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
            ("2026-01-01 00:05", 104, 105, 102, 103),
            ("2026-01-01 00:10", 103, 104, 99.8, 101),
            ("2026-01-01 00:15", 101, 106, 100.8, 105),
            ("2026-01-01 00:20", 105, 107, 103, 106),
            ("2026-01-01 00:25", 106, 106.5, 102, 103),
            ("2026-01-01 00:30", 103, 104, 100.2, 101.5),
            ("2026-01-01 00:35", 101.5, 105, 101, 104),
            ("2026-01-01 00:40", 104, 108, 103.5, 107),
            ("2026-01-01 00:45", 107, 109, 106, 108),
        ]
        pattern = engine._m5_pattern_v91(self._frame(rows), "BUY")
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern["name"], "DOUBLE_BOTTOM_BREAKOUT")
        self.assertEqual(pattern["direction"], "BUY")


if __name__ == "__main__":
    unittest.main()
