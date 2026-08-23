import unittest

import pandas as pd
from unittest.mock import patch

from replay_signal_history_v10_3 import aggregate_strategy_stats, replay_overall_status
import engine_v9_2 as engine


class ReplayV103ContractTests(unittest.TestCase):
    def test_aggregate_strategy_stats_counts_pass_fail_not_applicable_and_results(self):
        candidates = [
            {"strategy": "MOMENTUM", "direction": "BUY", "status": "PASS", "reason": ["SETUP_VALID"]},
            {"strategy": "BREAKOUT_RETEST", "direction": "BUY", "status": "FAIL", "reason": ["BREAKOUT_RETEST_SEQUENCE_NOT_CONFIRMED"]},
            {"strategy": "TREND_PULLBACK", "direction": "NEUTRAL", "status": "NOT_APPLICABLE", "reason": ["REGIME_RANGE_NOT_SUPPORTED"]},
        ]
        stats = aggregate_strategy_stats(candidates, {"MOMENTUM": "WIN"})
        self.assertEqual(stats["MOMENTUM"]["evaluated"], 1)
        self.assertEqual(stats["MOMENTUM"]["pass"], 1)
        self.assertEqual(stats["MOMENTUM"]["wins"], 1)
        self.assertEqual(stats["BREAKOUT_RETEST"]["fail"], 1)
        self.assertEqual(stats["TREND_PULLBACK"]["not_applicable"], 1)

    def test_overall_status_is_partial_when_only_one_symbol_fails(self):
        self.assertEqual(replay_overall_status([{"status": "completed"}, {"status": "failed"}]), "partial")
        self.assertEqual(replay_overall_status([{"status": "failed"}, {"status": "failed"}]), "failed")
        self.assertEqual(replay_overall_status([{"status": "completed"}, {"status": "completed"}]), "completed")

    def test_v103_target_liquidity_call_uses_entry_price(self):
        rows = 100
        base = pd.Series(range(rows), dtype=float) + 100.0
        frame = pd.DataFrame({
            "datetime": pd.date_range("2026-08-01", periods=rows, freq="5min", tz="UTC"),
            "open": base,
            "high": base + 2.0,
            "low": base - 2.0,
            "close": base + 0.5,
            "volume": 1.0,
        })
        m5 = frame.iloc[-80:].reset_index(drop=True)
        m15 = frame.reset_index(drop=True)

        strategy_result = {
            "signal": "BUY",
            "valid": True,
            "strategy": "MOMENTUM",
            "regime": "TREND",
            "regime_detail": {"direction": "BUY"},
            "analysis_window": {"m5_setup_bars": 20},
            "trigger_candle_count": 3,
            "rejection_reasons": [],
        }
        with patch.object(engine._ms, "analyze", return_value=strategy_result):
            result = engine.analyze_structure_setup(m5, m15, len(m5) - 1)

        self.assertIn("trade_levels", result)
        self.assertIn("target_liquidity", result)
        self.assertNotEqual(result.get("target_liquidity"), None)


if __name__ == "__main__":
    unittest.main()
