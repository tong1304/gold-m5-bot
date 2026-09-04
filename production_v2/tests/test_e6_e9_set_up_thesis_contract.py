from production_v2 import e8_applicability_boundary as e8_boundary
from production_v2.evidence_collaboration_runtime import preserve_e6_thesis_contract


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


def test_e9_boundary_removes_stale_no_thesis_diagnostic_without_granting_trade():
    e6 = {
        "setup": "LIQUIDITY_REVERSAL",
        "direction": "BUY",
        "state": "SETUP_THESIS",
        "thesis_status": "FORMING",
        "watch_only": False,
    }
    e9 = {"decision": "NO_TRADE", "reason_codes": ["E9_FINAL_GOVERNANCE", "NO_SURVIVING_E6_THESIS"]}
    out = preserve_e6_thesis_contract(e6, e9)
    assert "NO_SURVIVING_E6_THESIS" not in out["reason_codes"]
    assert "E6_THESIS_SURVIVES" in out["reason_codes"]
    assert out["decision"] == "NO_TRADE"
    assert out["thesis_contract"]["e9_owns_final_decision"] is True
