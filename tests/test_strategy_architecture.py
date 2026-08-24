import unittest
from v11.setup_state import SetupState, build_setup_id, can_emit_entry
from v11.regime import allowed_engines_for_regime


class StrategyArchitectureTests(unittest.TestCase):
    def test_regime_routes_exactly_to_approved_engines(self):
        self.assertEqual(allowed_engines_for_regime("TREND"), {"E1","E2","E3","E4","E5"})
        self.assertEqual(allowed_engines_for_regime("RANGE"), {"E6","E7","E8"})
        self.assertEqual(allowed_engines_for_regime("TRANSITION"), {"E3","E4","E7"})

    def test_same_setup_and_trigger_is_duplicate(self):
        setup_id = build_setup_id("BTC", "TREND", "E2", "BUY", 100.0)
        state = SetupState()
        ok, reason = can_emit_entry(state, setup_id, "trigger-1", max_reentries=2)
        self.assertTrue(ok)
        state.record(setup_id, "trigger-1")
        ok, reason = can_emit_entry(state, setup_id, "trigger-1", max_reentries=2)
        self.assertFalse(ok)
        self.assertEqual(reason, "DUPLICATE_TRIGGER")

    def test_new_trigger_on_same_setup_is_reentry(self):
        setup_id = build_setup_id("BTC", "TREND", "E2", "BUY", 100.0)
        state = SetupState()
        state.record(setup_id, "trigger-1")
        ok, reason = can_emit_entry(state, setup_id, "trigger-2", max_reentries=2)
        self.assertTrue(ok)
        self.assertEqual(reason, "RE_ENTRY")

    def test_new_setup_is_initial(self):
        state = SetupState()
        old_setup = build_setup_id("BTC", "TREND", "E2", "BUY", 100.0)
        new_setup = build_setup_id("BTC", "TREND", "E2", "BUY", 110.0)
        state.record(old_setup, "trigger-1")
        ok, reason = can_emit_entry(state, new_setup, "trigger-1", max_reentries=2)
        self.assertTrue(ok)
        self.assertEqual(reason, "INITIAL")

    def test_reentry_limit_is_enforced(self):
        setup_id = build_setup_id("BTC", "TREND", "E2", "BUY", 100.0)
        state = SetupState()
        state.record(setup_id, "trigger-1")
        state.record(setup_id, "trigger-2")
        ok, reason = can_emit_entry(state, setup_id, "trigger-3", max_reentries=1)
        self.assertFalse(ok)
        self.assertEqual(reason, "MAX_REENTRIES_REACHED")


if __name__ == "__main__":
    unittest.main()
