import unittest


class TestEngineV8RiskGuard(unittest.TestCase):
    def test_engine_v8_imports_and_exposes_risk_guard(self):
        import engine_v8

        self.assertTrue(callable(engine_v8.evaluate_live_risk_guard))
        result = engine_v8.evaluate_live_risk_guard()
        self.assertIsInstance(result, dict)
        self.assertTrue(result["allowed"])

    def test_risk_guard_blocks_configured_consecutive_losses(self):
        import engine_v8

        result = engine_v8.evaluate_live_risk_guard(
            consecutive_losses=3,
            max_consecutive_losses=3,
        )
        self.assertFalse(result["allowed"])
        self.assertIn("MAX_CONSECUTIVE_LOSSES", result["reasons"])


if __name__ == "__main__":
    unittest.main()
