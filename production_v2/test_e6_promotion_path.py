from production_v2.contracts import EngineResult
from production_v2.e6_pending_event_surgery import _candidate, _promotion_ready


def _result(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def test_e6_promotes_only_when_closed_candle_evidence_is_complete():
    upstream = {
        "E1": _result("E1", {"directional_pressure": "BUY"}),
        "E2": _result("E2", {
            "direction": "BUY",
            "opportunity_maturity": "CONFIRMED",
            "finding": "BUY opportunity confirmed from closed-candle evidence",
        }),
        "E3": _result("E3", {
            "external_state": "BUY",
            "internal_state": "BUY",
            "protected_completeness": "COMPLETE",
            "protected_active_regime": "BUY",
        }),
        "E4": _result("E4", {
            "event": "LOW_SWEEP_REJECTION",
            "event_id": "2026-09-06T11:30:00Z|LOW_SWEEP_REJECTION|LOW|79900|UP",
            "response_actor": "BUYERS",
            "auction_state": "CONFIRMED",
            "follow_through": True,
        }),
        "E5": _result("E5", {
            "finding": "FAVORABLE_LOCATION value=DISCOUNT response=REJECTED_BELOW_VALUE",
            "preferred_location": "LONG",
            "available_space_atr_long": 1.25,
            "available_space_atr_short": 0.40,
        }),
    }

    candidate = _candidate(upstream)
    assert candidate is not None
    assert _promotion_ready(candidate)
    assert "E2_OPPORTUNITY_CONFIRMATION" not in candidate["missing"]
    assert "E4_AUCTION_FOLLOW_THROUGH" not in candidate["missing"]
    assert "E3_INTERNAL_STRUCTURE_ALIGNMENT" not in candidate["missing"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" not in candidate["missing"]


def test_e6_does_not_promote_pending_auction_or_constrained_space():
    upstream = {
        "E1": _result("E1", {"directional_pressure": "BUY"}),
        "E2": _result("E2", {"direction": "BUY", "opportunity_maturity": "CONFIRMED"}),
        "E3": _result("E3", {
            "external_state": "BUY", "internal_state": "BUY",
            "protected_completeness": "COMPLETE", "protected_active_regime": "BUY",
        }),
        "E4": _result("E4", {
            "event": "LOW_SWEEP_REJECTION", "response_actor": "BUYERS",
            "auction_state": "PENDING", "follow_through": False,
        }),
        "E5": _result("E5", {
            "finding": "FAVORABLE_LOCATION value=DISCOUNT",
            "preferred_location": "LONG", "available_space_atr_long": 0.50,
        }),
    }
    candidate = _candidate(upstream)
    assert candidate is not None
    assert not _promotion_ready(candidate)
    assert "E4_AUCTION_FOLLOW_THROUGH" in candidate["missing"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in candidate["missing"]
