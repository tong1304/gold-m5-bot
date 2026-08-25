import unittest

from v11.strategy_scoring import STRATEGY_PROFILES, score_setup
from v11.regime import strategy_allowed_by_regime


class AssetStrategyArchitectureTests(unittest.TestCase):
    def test_gold_and_btc_have_three_distinct_asset_specific_profiles(self):
        self.assertEqual(set(STRATEGY_PROFILES), {"G1", "G2", "G3", "B1", "B2", "B3"})
        self.assertEqual({p["asset"] for p in STRATEGY_PROFILES.values() if p["asset"] == "GOLD"}, {"GOLD"})
        self.assertEqual({p["asset"] for p in STRATEGY_PROFILES.values() if p["asset"] == "BTC"}, {"BTC"})

    def test_core_gate_is_separate_from_score(self):
        profile = STRATEGY_PROFILES["G1"]
        self.assertTrue(profile["core_gate"])
        result = score_setup("G1", {"trend_strength": 15, "pullback_quality": 25})
        self.assertEqual(result["score"], 40)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["failed_gate"], [])

    def test_score_threshold_is_not_all_or_nothing(self):
        result = score_setup("G1", {
            "trend_strength": 15,
            "ema_alignment": 15,
            "pullback_quality": 25,
            "structure_quality": 10,
        })
        self.assertEqual(result["score"], 65)
        self.assertTrue(result["qualified"])

    def test_filter_can_reject_even_when_setup_score_passes(self):
        result = score_setup("B3", {
            "breakout_strength": 20,
            "volatility_expansion": 20,
            "momentum": 15,
            "candle_quality": 10,
            "location": 10,
            "distance_from_breakout": 10,
            "trend_alignment": 10,
            "volume_activity": 5,
            "filters": {"overextended": True},
        })
        self.assertEqual(result["score"], 100)
        self.assertFalse(result["qualified"])
        self.assertIn("OVEREXTENDED", result["filter_rejections"])

    def test_regime_selects_asset_specific_strategies(self):
        self.assertTrue(strategy_allowed_by_regime("GOLD", "G1", "TREND"))
        self.assertTrue(strategy_allowed_by_regime("GOLD", "G2", "TREND"))
        self.assertTrue(strategy_allowed_by_regime("GOLD", "G3", "BREAKOUT"))
        self.assertTrue(strategy_allowed_by_regime("BTC", "B1", "RANGE"))
        self.assertTrue(strategy_allowed_by_regime("BTC", "B2", "BREAKOUT_RETEST"))
        self.assertTrue(strategy_allowed_by_regime("BTC", "B3", "EXPANSION"))
        self.assertFalse(strategy_allowed_by_regime("BTC", "B1", "TREND"))
        self.assertFalse(strategy_allowed_by_regime("GOLD", "G1", "RANGE"))


if __name__ == "__main__":
    unittest.main()
