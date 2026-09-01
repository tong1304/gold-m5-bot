from production_v2.contracts import EngineResult
from production_v2.e3_brain import _protected
from production_v2.e9_brain import analyze_e9


def _engine(engine_id, output=None, reasons=()):
    return EngineResult(engine_id, engine_id, False, 0.0, output or {}, tuple(reasons))


def test_e3_rejects_inverted_protected_geometry():
    highs = [
        {"index": 8, "price": 120.0, "confirmation_index": 10, "status": "CONFIRMED", "label": "HH"},
        {"index": 12, "price": 100.0, "confirmation_index": 14, "status": "CONFIRMED", "label": "LH"},
    ]
    lows = [
        {"index": 9, "price": 110.0, "confirmation_index": 11, "status": "CONFIRMED", "label": "HL"},
        {"index": 13, "price": 90.0, "confirmation_index": 15, "status": "CONFIRMED", "label": "LL"},
    ]
    result = _protected(highs, lows)
    assert result["integrity"] == "INVALID"
    assert "PROTECTED_HIGH_LE_PROTECTED_LOW" in result["integrity_reasons"]
    assert result["protected_high"] is None
    assert result["protected_low"] is None


def test_e9_no_thesis_does_not_inherit_e8_economic_blockers():
    upstream = {
        "E1": _engine("E1", {"pressure": "DOWN"}),
        "E2": _engine("E2", {"finding": "NEUTRAL"}),
        "E3": _engine("E3", {"structure_integrity": "VALID", "lifecycle": "TRANSITION"}),
        "E4": _engine("E4", {"event": "LOW_SWEEP_REJECTION", "auction_state": "PENDING"}),
        "E5": _engine("E5", {"value_response": "ACCEPTED_BELOW_VALUE"}),
        "E6": _engine("E6", {"finding": "No causal setup hypothesis survives current closed-candle evidence.", "reasons": ["STRUCTURAL_SPACE_INSUFFICIENT"]}),
        "E7": _engine("E7", {"finding": "CONFIRMATION_NOT_APPLICABLE"}),
        "E8": _engine("E8", {"economic_state": "UNRESOLVED", "economic_blockers": ["REAL_RR_BELOW_MINIMUM", "HISTORICAL_SAMPLE_INSUFFICIENT"]}),
    }
    result = analyze_e9({}, upstream)
    assert result.output["decision"] == "NO_TRADE"
    assert result.output["final_governance"] == "NO_THESIS"
    assert result.output["confirmation_state"] == "NOT_APPLICABLE"
    assert result.output["economic_state"] == "NOT_APPLICABLE"
    assert result.output["economic_blockers"] == []
    assert "REAL_RR_BELOW_MINIMUM" not in result.output["reason_codes"]
    assert "HISTORICAL_SAMPLE_INSUFFICIENT" not in result.output["reason_codes"]
    assert result.output["reason_scope"] == "E6_THESIS_GATE_ONLY"


def test_e9_blocks_invalid_e3_structure_when_thesis_exists():
    upstream = {
        "E1": _engine("E1", {"pressure": "UP"}),
        "E2": _engine("E2", {"direction": "BUY"}),
        "E3": _engine("E3", {"structure_integrity": "INVALID", "protected_structure": {"integrity": "INVALID", "integrity_reasons": ["PROTECTED_HIGH_LE_PROTECTED_LOW"]}}),
        "E4": _engine("E4", {"finding": "LOW_SWEEP_REJECTION"}),
        "E5": _engine("E5", {"value_response": "ACCEPTED_ABOVE_VALUE"}),
        "E6": _engine("E6", {"direction": "BUY", "setup": "LIQUIDITY_REVERSAL", "thesis": "BUY hypothesis", "thesis_state": "HYPOTHESIS"}),
        "E7": _engine("E7", {"confirmation_state": "PENDING"}),
        "E8": _engine("E8", {"economic_state": "UNRESOLVED"}),
    }
    result = analyze_e9({}, upstream)
    assert result.output["decision"] == "NO_TRADE"
    assert "STRUCTURE_INTEGRITY_INVALID" in result.output["hard_conflicts"]
    assert result.output["final_governance"] == "REJECTED_HARD_CONFLICT"
    assert result.output["execution_state"] == "BLOCKED"
