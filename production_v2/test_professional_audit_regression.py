from production_v2.professional_brain_audit import audit_all, opportunity_potential
from production_v2.professional_governance import audit_engines


def test_future_invalidation_catalog_does_not_become_governance_veto():
    results = {
        "E1": {"analysis_status": "COMPLETE", "state": "TRANSITION", "invalidations": ["data_quality_failure", "trend_alignment_break"]},
        "E2": {"state": "UNRESOLVED", "missing_evidence": ["auction acceptance"]},
        "E3": {"state": "ESTABLISHED", "lifecycle": "ESTABLISHED"},
        "E4": {"auction_state": "PENDING"},
        "E5": {"location_state": "FAVORABLE", "repricing_state": "REPRICING_FAILED"},
        "E6": {"state": "VALIDATING"},
        "E7": {"confirmation_state": "PENDING"},
        "E8": {"risk_state": "UNRESOLVED"},
        "E9": {"decision": "NO_TRADE"},
    }
    audit = audit_engines(results)
    assert audit["hard_veto"] is False
    assert audit["hard_vetoes"] == []
    assert audit["pending_gates"]


def test_explicit_active_invalidation_remains_hard():
    results = {
        "E1": {"analysis_status": "COMPLETE", "active_invalidations": ["DATA_QUALITY_FAILURE"]},
    }
    audit = audit_engines(results)
    assert audit["hard_veto"] is True
    assert "E1:DATA_QUALITY_FAILURE" in audit["hard_vetoes"]


def test_nine_brain_audit_covers_all_engines():
    outputs = {engine: {"finding": "OBSERVED"} for engine in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")}
    audit = audit_all(outputs)
    assert tuple(audit["per_engine"]) == ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
    assert 0.0 <= audit["overall_score"] <= 100.0


def test_opportunity_potential_is_conservative_when_geometry_is_missing():
    outputs = {
        "E5": {"available_space_atr_long": 0.55, "available_space_atr_short": 0.24},
        "E6": {"direction": "BUY", "setup": "LIQUIDITY_REVERSAL"},
        "E7": {"confirmation_state": "PENDING"},
        "E8": {"trade_plan": {}},
        "E9": {"all_gates_pass": False},
    }
    opportunity = opportunity_potential(outputs)
    assert opportunity["executable"] is False
    assert opportunity["do_not_execute"] is True
    assert opportunity["available_space_atr"] == 0.55
