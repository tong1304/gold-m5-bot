import os
import tempfile
import unittest

import pandas as pd


class V8ArchitectureTests(unittest.TestCase):
    def test_engine_v8_is_standalone_and_exposes_runtime_interface(self):
        import engine_v8
        self.assertEqual(engine_v8.ENGINE_VERSION, "8.0")
        self.assertIs(engine_v8.app, engine_v8.base.app)
        self.assertTrue(callable(engine_v8.evaluate_live_risk_guard))
        self.assertTrue(callable(engine_v8.send_telegram))
        self.assertTrue(callable(engine_v8.calculate_indicators))

    def test_live_scanner_uses_lse_helpers(self):
        import live_scanner
        self.assertEqual(live_scanner.SYMBOL_MAP["BTC"], "BTC/USD")
        self.assertEqual(live_scanner.SYMBOL_MAP["GOLD"], "XAU/USD")
        self.assertTrue(callable(live_scanner._lse_frame))
        self.assertTrue(callable(live_scanner.scan_once))

    def test_scheduler_is_lse_provider(self):
        import scheduler
        self.assertEqual(scheduler.status()["provider"], "LSE")
        self.assertEqual(set(scheduler.status()["symbols"]), {"BTC", "GOLD"})

    def test_statistics_page_is_v8_and_shows_no_trade(self):
        import statistics_page
        self.assertIn("Signal Statistics V8", statistics_page.PAGE)
        self.assertIn("NO TRADE", statistics_page.PAGE)
        self.assertIn("no_trade", statistics_page.PAGE)

    def test_engine_returns_explicit_no_trade_without_context(self):
        import engine_v8
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "datetime"])
        result = engine_v8.analyze_structure_setup(empty, empty, empty, 0)
        self.assertEqual(result["signal"], "NO_TRADE")
        self.assertFalse(result["valid"])
        self.assertIn("INSUFFICIENT_CONTEXT", result["rejection_reasons"])

    def test_no_trade_history_is_counted(self):
        from signal_history import SignalHistory
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "signals.db")
            store = SignalHistory(db)
            inserted = store.record_no_trade({
                "signal_id": "TEST-NOTRADE-1",
                "symbol": "BTC",
                "candle_time": "2026-08-23T12:00:00+00:00",
                "rejection_reasons": ["NO_LIQUIDITY_SWEEP"],
            })
            self.assertTrue(inserted)
            stats = store.statistics(days=3650)
            self.assertEqual(stats["no_trade"], 1)
            self.assertEqual(stats["total"], 1)
            self.assertEqual(stats["trade_count"], 0)


if __name__ == "__main__":
    unittest.main()
