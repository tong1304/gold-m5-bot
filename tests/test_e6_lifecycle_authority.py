import os

os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"

from production_v2 import pipeline
from production_v2.contracts import EngineResult


def test_concrete_e6_thesis_is_lifecycle_candidate_even_with_reconciliation_blockers():
    results = {
        "E6": EngineResult("E6", "Setup Formation Reasoner", False, 70.0, {
            "setup": "BREAKOUT_RETEST",
            "setup_family": "BREAKOUT_RETEST",
            "setup_exists": True,
            "setup_state": "VALIDATING",
            "direction": "BUY",
            "e6_causal_gate": "PASSED",
            "missing_proof": ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"],
            "trade_ready": False,
        }),
        "E7": EngineResult("E7", "Confirmation Analyst", False, 40.0, {
            "confirmation_state": "DEVELOPING",
            "confirmation": "DEVELOPING",
        }),
        "E8": EngineResult("E8", "Trade Economics Risk", None, 0.0, {
            "profit_edge": {"trusted": False, "blockers": ["REAL_RR_BELOW_MINIMUM"]},
        }),
        "E9": EngineResult("E9", "Master Governance", False, 0.0, {"decision": "NO_TRADE"}),
    }

    current, leader, competition = pipeline._directional_lifecycle_current(
        results,
        "NO_TRADE",
        False,
        "2026-09-03T16:05:00Z",
        {},
    )

    buy = current["BUY"]
    assert buy["candidate"] is True
    assert buy["lifecycle_source"] == "E6_SETUP"
    assert buy["direction"] == "BUY"
    assert buy["setup"] == "BREAKOUT_RETEST"
    # setup_state is the canonical E6 field at the pipeline boundary; accept
    # thesis_status as a compatibility alias when a producer supplies it.
    assert buy.get("thesis_status", buy.get("setup_state")) == "VALIDATING"
    assert "E4_AUCTION_FOLLOW_THROUGH" in buy["wait_for"]
    assert buy["ready"] is False
    assert leader == "BUY"
    assert competition in {"UNCONTESTED", "CONTESTED"}
