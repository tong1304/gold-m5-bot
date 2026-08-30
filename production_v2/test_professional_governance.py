from professional_governance import audit_engines, enforce_final_authority


def _base():
    return {engine: {} for engine in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")}


def test_transition_pending_confirmation_and_bad_geometry_block():
    results = _base()
    results["E1"] = {"market_state": "TREND_UP", "direction": "UP"}
    results["E3"] = {"structure_lifecycle": "TRANSITION", "direction": "NEUTRAL"}
    results["E4"] = {"auction_state": "PENDING", "direction": "UP"}
    results["E7"] = {"confirmation_passed": False}
    results["E8"] = {"trade_economics_valid": False}
    results["E9"] = {"decision": "BUY"}

    audit = audit_engines(results)
    decision, approved, reasons = enforce_final_authority(results["E9"], audit)

    assert audit["hard_veto"] is True
    assert "STRUCTURE_NOT_RESOLVED" in audit["hard_vetoes"]
    assert "AUCTION_CONFIRMATION_PENDING" in audit["hard_vetoes"]
    assert "ENTRY_CONFIRMATION_NOT_PROVEN" in audit["hard_vetoes"]
    assert "TRADE_ECONOMICS_NOT_VALID" in audit["hard_vetoes"]
    assert decision == "NO_TRADE"
    assert approved is False
    assert "NINE_BRAIN_GOVERNANCE_BLOCKED" in reasons


def test_directional_conflict_is_a_hard_veto():
    results = _base()
    results["E1"] = {"direction": "UP"}
    results["E3"] = {"direction": "DOWN", "structure_lifecycle": "ESTABLISHED"}
    audit = audit_engines(results)
    assert audit["directional_conflict"] is True
    assert "DIRECTIONAL_EVIDENCE_CONFLICT" in audit["hard_vetoes"]


def test_clean_chain_can_reach_e9_authority_check():
    results = _base()
    results["E1"] = {"direction": "UP", "market_state": "TREND_UP"}
    results["E3"] = {"direction": "UP", "structure_lifecycle": "ESTABLISHED"}
    results["E4"] = {"direction": "UP", "auction_state": "CONFIRMED"}
    results["E7"] = {"confirmation_passed": True}
    results["E8"] = {"trade_economics_valid": True}
    results["E9"] = {"decision": "BUY"}
    audit = audit_engines(results)
    decision, approved, _ = enforce_final_authority(results["E9"], audit)
    assert audit["hard_veto"] is False
    assert decision == "BUY"
    assert approved is True
