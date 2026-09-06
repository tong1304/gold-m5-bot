from production_v2.bootstrap_surgery import _promote_independent_e6
from production_v2.contracts import EngineResult


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def _watch_result(*_args, **_kwargs):
    return _engine("E6", {
        "setup": "OPPORTUNITY_WATCH",
        "setup_family": "LIQUIDITY_RESPONSE",
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "direction": "BUY",
        "watch_only": True,
        "trade_ready": False,
        "setup_exists": False,
        "e6_causal_gate": "WATCH_ONLY",
        "state": "CONTESTED_WATCH",
        "setup_state": "CONTESTED_WATCH",
        "thesis_status": "CONTESTED",
        "event_id": "evt-1",
        "reason_codes": ["E7_CONFIRMATION"],
    })


def _complete_upstream():
    return {
        "E1": _engine("E1", {"directional_pressure": "BUY", "pressure": "BULLISH"}),
        "E2": _engine("E2", {
            "direction": "BUY",
            "opportunity_maturity": "DEVELOPING",
            "finding": "AUCTION_REJECTION_CONFIRMED_OPPORTUNITY_DEVELOPING",
            "missing_evidence": [],
            "blockers": [],
        }),
        "E3": _engine("E3", {
            "external_state": "UP",
            "internal_state": "UP",
            "protected_completeness": "COMPLETE",
            "protected_active_regime": "UP",
            "structure_invalidated": False,
        }),
        "E4": _engine("E4", {
            "event": "LOW_SWEEP_REJECTION",
            "event_id": "evt-1",
            "response_actor": "BUYERS",
            "auction_state": "CONFIRMED",
            "reasons": [],
        }),
        "E5": _engine("E5", {
            "finding": "FAVORABLE_LOCATION",
            "value_state": "DISCOUNT",
            "preferred_location": "LONG",
            "available_space_atr_long": 1.25,
        }),
    }


def test_complete_closed_candle_evidence_promotes_watch_to_setup_thesis():
    result = _promote_independent_e6(_watch_result, {}, _complete_upstream())
    out = result.output
    assert out["setup_state"] == "SETUP_THESIS"
    assert out["setup_exists"] is True
    assert out["watch_only"] is False
    assert out["trade_ready"] is False
    assert out["e6_causal_gate"] == "PASSED"
    assert out["missing_proof"] == ["E7_CONFIRMATION"]


def test_pending_e4_cannot_promote():
    upstream = _complete_upstream()
    upstream["E4"] = _engine("E4", {
        "event": "LOW_SWEEP_REJECTION",
        "event_id": "evt-1",
        "response_actor": "BUYERS",
        "auction_state": "PENDING",
    })
    result = _promote_independent_e6(_watch_result, {}, upstream)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["setup_exists"] is False


def test_constrained_space_cannot_promote():
    upstream = _complete_upstream()
    upstream["E5"] = _engine("E5", {
        "finding": "FAVORABLE_LOCATION",
        "value_state": "DISCOUNT",
        "preferred_location": "LONG",
        "available_space_atr_long": 0.74,
    })
    result = _promote_independent_e6(_watch_result, {}, upstream)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["setup_exists"] is False


def test_unconfirmed_e2_cannot_promote():
    upstream = _complete_upstream()
    upstream["E2"] = _engine("E2", {
        "direction": "BUY",
        "opportunity_maturity": "DEVELOPING",
        "finding": "CONDITIONAL_DIRECTIONAL_OPPORTUNITY",
        "missing_evidence": ["closed-candle acceptance/follow-through proves the auction"],
        "blockers": ["AUCTION_CONFIRMATION_PENDING"],
    })
    result = _promote_independent_e6(_watch_result, {}, upstream)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["setup_exists"] is False


def test_mixed_internal_structure_cannot_promote():
    upstream = _complete_upstream()
    upstream["E3"] = _engine("E3", {
        "external_state": "UP",
        "internal_state": "MIXED",
        "protected_completeness": "COMPLETE",
        "protected_active_regime": "UP",
    })
    result = _promote_independent_e6(_watch_result, {}, upstream)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["setup_exists"] is False
