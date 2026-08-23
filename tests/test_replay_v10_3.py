import unittest

from replay_signal_history_v10_3 import aggregate_strategy_stats, replay_overall_status


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


if __name__ == "__main__":
    unittest.main()
