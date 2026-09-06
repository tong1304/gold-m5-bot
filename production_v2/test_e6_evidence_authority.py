from production_v2.contracts import EngineResult
from production_v2.e6_evidence_authority import normalize_e6_evidence
from production_v2.e6_pending_event_surgery import _reconcile_existing_watch_evidence


def _result(output):
    return EngineResult("E6", "Setup Brain", False, 0.0, output, ())


def _upstream(e3, e4):
    return {"E3": _result(e3), "E4": _result(e4)}


def test_low_liquidity_unclear_response_is_neutral_and_legacy_directional_evidence_is_removed():
    result = _result({
        "setup": "OPPORTUNITY_WATCH", "watch_only": True, "trade_ready": False, "direction": "BUY",
        "supporting_evidence": ["E1_DIRECTIONAL_CORE", "E4_DIRECTIONAL_AUCTION_EVIDENCE", "E5_LOCATION_VALUE_SUPPORT", "E3_EXTERNAL_STRUCTURE_SUPPORT"],
    })
    upstream = _upstream(
        {"external_state": "MIXED", "internal_state": "MIXED", "protected_completeness": "NO_DIRECTIONAL_REGIME", "protected_active_regime": "MIXED"},
        {"event": "LOW_LIQUIDITY_INTERACTION", "response_actor": "UNCLEAR", "directional_implication": "NEUTRAL", "direction": "NEUTRAL", "auction_state": "PENDING"},
    )
    out = normalize_e6_evidence(result, upstream).output
    assert "E4_DIRECTIONAL_AUCTION_EVIDENCE" not in out["supporting_evidence"]
    assert "E4_DIRECTIONAL_EVENT_OBSERVATION" not in out["supporting_evidence"]
    assert "E4_CONFIRMED_RESPONSE" not in out["supporting_evidence"]
    assert "E3_EXTERNAL_STRUCTURE_SUPPORT" not in out["supporting_evidence"]
    assert "E3_MIXED_CONTEXT" in out["supporting_evidence"]
    assert "E3_INTERNAL_MIXED_CONTEXT" in out["supporting_evidence"]


def test_confirmed_directional_auction_and_structure_keep_authoritative_evidence():
    result = _result({
        "setup": "OPPORTUNITY_WATCH", "watch_only": True, "trade_ready": False, "direction": "BUY",
        "supporting_evidence": ["E4_DIRECTIONAL_AUCTION_EVIDENCE", "E3_EXTERNAL_STRUCTURE_SUPPORT"],
    })
    upstream = _upstream(
        {"external_state": "BUY", "internal_state": "BUY", "protected_completeness": "COMPLETE", "protected_active_regime": "BUY"},
        {"event": "LOW_REJECTION", "auction_state": "CONFIRMED"},
    )
    out = normalize_e6_evidence(result, upstream).output
    assert "E4_DIRECTIONAL_EVENT_OBSERVATION" in out["supporting_evidence"]
    assert "E4_CONFIRMED_RESPONSE" in out["supporting_evidence"]
    assert "E3_EXTERNAL_STRUCTURE_SUPPORT" in out["supporting_evidence"]
    assert "E3_INTERNAL_STRUCTURE_ALIGNMENT" in out["supporting_evidence"]


def test_v8_reconciliation_accepts_multiple_direction_fields_without_type_error():
    result = _result({
        "setup": "OPPORTUNITY_WATCH", "watch_only": True, "trade_ready": False,
        "direction": "", "direction_thesis": "BUY", "thesis_direction": "SELL",
        "supporting_evidence": ["E4_DIRECTIONAL_AUCTION_EVIDENCE", "E3_INTERNAL_STRUCTURE_SUPPORT", "E3_EXTERNAL_STRUCTURE_SUPPORT"],
    })
    upstream = _upstream(
        {"external_state": "MIXED", "structure_direction": "BUY", "internal_state": "UP", "protected_completeness": "NO_DIRECTIONAL_REGIME", "protected_active_regime": "MIXED"},
        {"event": "LOW_SWEEP_REJECTION", "response_actor": "BUYERS", "auction_state": "PENDING"},
    )
    out = _reconcile_existing_watch_evidence(result, upstream).output
    assert out["evidence_attribution_authority"] == "E3_E4_FACTS"
    assert "E3_EXTERNAL_STRUCTURE_SUPPORT" not in out["supporting_evidence"]
    assert "E3_INTERNAL_STRUCTURE_SUPPORT" not in out["supporting_evidence"]
    assert "E3_INTERNAL_STRUCTURE_ALIGNMENT" in out["supporting_evidence"]
    assert "E3_MIXED_CONTEXT" in out["supporting_evidence"]
    assert "E4_DIRECTIONAL_EVENT_OBSERVATION" in out["supporting_evidence"]
    assert "E4_CONFIRMED_RESPONSE" not in out["supporting_evidence"]
