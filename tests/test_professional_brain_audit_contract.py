from production_v2.contracts import EngineResult
from production_v2.professional_brain_audit import audit_all


def test_audit_all_accepts_engine_result_mapping():
    outputs = {
        "E1": EngineResult("E1", "Market State Brain", True, 80.0, {"finding": "RANGE", "confidence": 0.8, "counter_evidence": []}),
        "E2": EngineResult("E2", "Opportunity Brain", False, 40.0, {"finding": "UNRESOLVED", "opportunity_state": "DEVELOPING", "missing_evidence": ["E2_PROOF"]}),
        "E3": EngineResult("E3", "Structure Brain", False, 40.0, {"finding": "MIXED", "lifecycle": "TRANSITION", "protected_high": 101, "protected_low": 99}),
        "E4": EngineResult("E4", "Liquidity Brain", False, 40.0, {"finding": "PENDING", "auction_state": "PENDING", "auction_quality": 40}),
        "E5": EngineResult("E5", "Location Brain", False, 40.0, {"finding": "WAIT", "location_state": "EQUILIBRIUM", "repricing_state": "PENDING"}),
        "E6": EngineResult("E6", "Setup Brain", False, 40.0, {"finding": "WATCH", "setup_state": "FORMING"}),
        "E7": EngineResult("E7", "Confirmation Brain", False, 40.0, {"finding": "WAIT", "confirmation_state": "PENDING"}),
        "E8": EngineResult("E8", "Economics Brain", False, 40.0, {"finding": "NOT_APPLICABLE", "risk_state": "NOT_APPLICABLE"}),
        "E9": EngineResult("E9", "Master Decision Brain", False, 0.0, {"decision": "NO_TRADE", "decision_state": "CONTROLLED_WAIT", "market_control": {}}),
    }

    audit = audit_all(outputs)

    assert set(audit["per_engine"]) == set(outputs)
    assert audit["per_engine"]["E9"]["contract_completeness"] >= 0
