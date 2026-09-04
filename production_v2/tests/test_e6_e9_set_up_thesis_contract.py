from production_v2 import e8_applicability_boundary as e8_boundary
from production_v2 import e7_thesis_boundary as boundary
from production_v2.contracts import EngineResult


def test_e8_accepts_concrete_setup_thesis_even_with_legacy_no_causal_diagnostic():
    e6 = {
        "setup": "LIQUIDITY_REVERSAL",
        "direction": "BUY",
        "state": "SETUP_THESIS",
        "thesis_status": "FORMING",
        "watch_only": False,
        "trade_ready": False,
        "reason_codes": ["NO_CAUSAL_OPPORTUNITY"],
    }
    assert e8_boundary._has_surviving_thesis(e6) is True


def test_e7_boundary_preserves_explicit_setup_thesis_when_legacy_e7_returns_watch():
    e6 = {
        "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
        "direction": "SELL",
        "state": "SETUP_THESIS",
        "thesis_status": "FORMING",
        "candidate_type": "SETUP_CANDIDATE",
        "watch_only": False,
        "trade_ready": False,
        "gate_passed": False,
    }
    legacy_watch = EngineResult(
        "E7", "Confirmation / Trigger Brain", False, 0.0,
        {
            "state": "WAIT",
            "confirmation": "UNRESOLVED",
            "confirmation_state": "NOT_APPLICABLE",
            "setup": "NONE",
            "setup_family": "NONE",
            "reason_codes": ["CONFIRMATION_NOT_APPLICABLE", "E7_DID_NOT_CREATE_THESIS", "E6_OPPORTUNITY_WATCH_NOT_SETUP"],
        },
        ("CONFIRMATION_NOT_APPLICABLE", "E7_DID_NOT_CREATE_THESIS", "E6_OPPORTUNITY_WATCH_NOT_SETUP"),
    )

    result = boundary.enforce_e6_thesis_boundary(
        lambda snapshot, upstream: legacy_watch,
        {"bars": [{"close": 1.0}] * 5},
        {"E6": EngineResult("E6", "Setup Brain", False, 0.0, e6, ())},
    )
    assert result.output["setup"] == "AUCTION_ACCEPTANCE_CONTINUATION"
    assert result.output["setup_family"] == "AUCTION_ACCEPTANCE_CONTINUATION"
    assert result.output["direction"] == "SELL"
    assert result.output["trigger_status"] != "NOT_ALLOWED"
    assert "E6_OPPORTUNITY_WATCH_NOT_SETUP" not in result.output["reason_codes"]
    assert result.output["thesis_boundary"]["e6_owns_thesis"] is True
