from production_v2.contracts import EngineResult
from production_v2.e6_pending_event_surgery import _candidate, _promotion_ready


def _r(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def _upstream(*, e2_maturity="CONFIRMED", auction="CONFIRMED", follow=True, space_long=1.25):
    return {
        "E1": _r("E1", {"directional_pressure": "BUY"}),
        "E2": _r("E2", {
            "direction": "BUY",
            "opportunity_maturity": e2_maturity,
            "finding": "BUY opportunity confirmed from closed-candle evidence" if e2_maturity == "CONFIRMED" else "BUY opportunity is developing",
        }),
        "E3": _r("E3", {
            "external_state": "BUY",
            "internal_state": "BUY",
            "protected_completeness": "COMPLETE",
            "protected_active_regime": "BUY",
        }),
        "E4": _r("E4", {
            "event": "LOW_SWEEP_REJECTION",
            "event_id": "2026-09-06T11:30:00Z|LOW_SWEEP_REJECTION|LOW|79900|UP",
            "response_actor": "BUYERS",
            "auction_state": auction,
            "follow_through": follow,
        }),
        "E5": _r("E5", {
            "finding": "FAVORABLE_LOCATION value=DISCOUNT response=REJECTED_BELOW_VALUE",
            "preferred_location": "LONG",
            "available_space_atr_long": space_long,
            "available_space_atr_short": 0.40,
        }),
    }


def test_e6_promotion_gate_accepts_complete_upstream_evidence():
    candidate = _candidate(_upstream())
    assert candidate is not None
    assert _promotion_ready(candidate)
    assert candidate["direction"] == "BUY"
    assert "E2_OPPORTUNITY_CONFIRMATION" not in candidate["missing"]
    assert "E4_AUCTION_FOLLOW_THROUGH" not in candidate["missing"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" not in candidate["missing"]
    assert "E3_INTERNAL_STRUCTURE_ALIGNMENT" in candidate["support"]
    assert "E4_CONFIRMED_RESPONSE" in candidate["support"]


def test_e6_promotion_gate_rejects_pending_auction():
    candidate = _candidate(_upstream(auction="PENDING", follow=False))
    assert candidate is not None
    assert not _promotion_ready(candidate)
    assert "E4_AUCTION_FOLLOW_THROUGH" in candidate["missing"]


def test_e6_promotion_gate_rejects_constrained_space():
    candidate = _candidate(_upstream(space_long=0.50))
    assert candidate is not None
    assert not _promotion_ready(candidate)
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in candidate["missing"]


def test_e6_promotion_gate_rejects_unresolved_e2():
    candidate = _candidate(_upstream(e2_maturity="UNRESOLVED"))
    assert candidate is not None
    assert not _promotion_ready(candidate)
    assert "E2_OPPORTUNITY_CONFIRMATION" in candidate["missing"]


# Trigger the guarded surgery workflow after its creation; the workflow itself
# patches production_v2/e6_pending_event_surgery.py and commits only after tests pass.
