from production_v2.e8_brain import analyze_e8


def test_e8_does_not_emit_trade_economics_without_e6_thesis():
    e6 = {
        "setup": "OPPORTUNITY_WATCH",
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "watch_only": True,
        "trade_ready": False,
        "trade_permission": False,
        "gate_passed": False,
        "direction": "BUY",
        "finding": "BUY opportunity is forming; causal evidence exists but trade setup is not yet proven.",
        "missing_proof": ["E7_CONFIRMATION", "STRUCTURAL_SPACE_INSUFFICIENT"],
        "reason_codes": ["E7_CONFIRMATION", "STRUCTURAL_SPACE_INSUFFICIENT"],
    }
    e7 = {
        "setup": "OPPORTUNITY_WATCH",
        "confirmation": "NOT_APPLICABLE",
        "gate_passed": False,
        "trade_ready": False,
    }
    out = analyze_e8(e6=e6, e7=e7).to_dict()

    assert out["gate_passed"] is False
    assert out.get("trade_ready") is not True
    reasons = set(out.get("reason_codes") or out.get("reasons") or [])
    assert "E6_THESIS_REQUIRED" in reasons
