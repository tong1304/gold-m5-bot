import os

os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"

from production_v2.app import _current_opportunity_input
from production_v2.contracts import DecisionResult, EngineResult


def test_concrete_e6_thesis_is_lifecycle_candidate_even_with_reconciliation_blockers():
    engines = (
        EngineResult("E6", "Setup Formation Reasoner", False, 70.0, {
            "setup": "BREAKOUT_RETEST",
            "setup_family": "BREAKOUT_RETEST",
            "setup_exists": True,
            "setup_state": "VALIDATING",
            "direction": "BUY",
            "e6_causal_gate": "PASSED",
            "missing_proof": ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"],
            "trade_ready": False,
        }),
        EngineResult("E7", "Confirmation Analyst", False, 40.0, {
            "confirmation_state": "DEVELOPING",
            "confirmation": "DEVELOPING",
        }),
        EngineResult("E8", "Trade Economics Risk", None, 0.0, {
            "profit_edge": {"trusted": False, "blockers": ["REAL_RR_BELOW_MINIMUM"]},
        }),
        EngineResult("E9", "Master Governance", False, 0.0, {
            "decision": "NO_TRADE",
        }),
    )
    result = DecisionResult(symbol="BTC/USD", timeframe="M5", engines=engines)

    current = _current_opportunity_input(result, "2026-09-03T16:05:00Z")

    assert current["candidate"] is True
    assert current["lifecycle_source"] == "E6_SETUP"
    assert current["direction"] == "BUY"
    assert current["setup"] == "BREAKOUT_RETEST"
    assert current["thesis_status"] == "VALIDATING"
    assert "E4_AUCTION_FOLLOW_THROUGH" in current["wait_for"]
    assert current["ready"] is False
