from production_v2.nine_brain_surgery import harden_all, harden_engine


def test_future_invalidations_are_not_current_blockers():
    out = harden_engine("E1", {
        "analysis_status": "COMPLETE",
        "reason_codes": ["DATA_INTEGRITY_VALIDATED"],
        "invalidations": ["data_quality_failure", "trend_alignment_break"],
    })
    assert out["active_reason_codes"] == ["DATA_INTEGRITY_VALIDATED"]
    assert out["active_invalidations"] == []
    assert out["future_invalidation_conditions"] == ["DATA_QUALITY_FAILURE", "TREND_ALIGNMENT_BREAK"]
    assert out["professional_contract"]["decision_authority"] == "E9_ONLY"


def test_transition_is_not_invalidation():
    out = harden_engine("E3", {
        "lifecycle": "TRANSITION",
        "reason_codes": ["CAUSAL_STRUCTURE_ANALYSIS"],
    })
    assert out["transition_is_not_invalidation"] is True
    assert out["professional_contract"]["lifecycle"] == "TRANSITION"


def test_all_nine_have_explicit_contract():
    outputs = harden_all({engine: {} for engine in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")})
    assert tuple(outputs) == ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
    for engine, output in outputs.items():
        assert output["professional_contract"]["engine"] == engine
        assert output["professional_contract"]["decision_authority"] == "E9_ONLY"
        assert output["professional_contract"]["can_authorize_entry"] is False
        assert output["professional_contract"]["closed_candle_only"] is True


def test_e4_pending_remains_pending():
    out = harden_engine("E4", {
        "auction_state": "PENDING",
        "reason_codes": ["ACCEPTANCE_REQUIRES_FOLLOW_THROUGH"],
    })
    assert out["auction_confirmation_proven"] is False
    assert out["auction_confirmation_pending"] is True
