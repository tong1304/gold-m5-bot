import tempfile
import unittest

from signal_history import SignalHistory


class SignalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db.close()
        self.history = SignalHistory(self.db.name)

    def tearDown(self):
        import os
        os.unlink(self.db.name)

    def test_record_signal_and_statistics(self):
        self.history.record_signal({
            "signal_id": "BTC-1",
            "symbol": "BTC",
            "signal": "BUY",
            "closed_candle": "2026-08-23 06:35:00+00:00",
            "trade_levels": {"entry": 100, "sl": 90, "tp": 120, "risk_reward": 2},
        })
        self.history.set_result("BTC-1", "WIN", 2.0, "2026-08-23T07:00:00+00:00")
        stats = self.history.statistics()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["losses"], 0)
        self.assertEqual(stats["win_rate"], 100.0)
        self.assertEqual(stats["net_r"], 2.0)

    def test_update_open_signal_from_future_candles(self):
        self.history.record_signal({
            "signal_id": "SELL-1",
            "symbol": "GOLD",
            "signal": "SELL",
            "closed_candle": "2026-08-23T06:35:00+00:00",
            "trade_levels": {"entry": 100, "sl": 110, "tp": 80, "risk_reward": 2},
        })
        candles = [
            {"datetime": "2026-08-23T06:40:00+00:00", "high": 104, "low": 95, "close": 98},
            {"datetime": "2026-08-23T06:45:00+00:00", "high": 101, "low": 79, "close": 82},
        ]
        updated = self.history.evaluate_candles("SELL-1", candles)
        self.assertEqual(updated["result"], "WIN")
        self.assertEqual(updated["r_multiple"], 2.0)


if __name__ == "__main__":
    unittest.main()
