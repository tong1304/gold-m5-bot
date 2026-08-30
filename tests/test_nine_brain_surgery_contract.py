from production_v2.nine_brain_surgery import harden_engine


def test_each_brain_exposes_explicit_gate_contract():
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"):
        output = harden_engine(engine_id, {})
        contract = output["professional_contract"]
        assert contract["engine"] == engine_id
        assert contract["closed_candle_only"] is True
        assert contract["decision_authority"] == "E9_ONLY"
        assert "gate_state" in contract
        assert "blockers" in contract


def test_pending_auction_is_not_a_confirmed_gate():
    output = harden_engine("E4", {
        "auction_state": "PENDING",
        "invalidations": ["FUTURE_FAILURE"],
    })
    assert output["auction_confirmation_proven"] is False
    assert output["professional_contract"]["gate_state"] == "PENDING"
    assert "FUTURE_FAILURE" in output["future_invalidation_conditions"]
    assert "FUTURE_FAILURE" not in output["active_invalidations"]


def test_e8_never_authorizes_execution_and_reports_economic_blockers():
    output = harden_engine("E8", {
        "risk_state": "UNRESOLVED",
        "economic_blockers": ["REAL_RR_BELOW_MINIMUM"],
    })
    assert output["execution_authorization"] == "NONE"
    assert output["professional_contract"]["gate_state"] == "BLOCKED"
    assert "REAL_RR_BELOW_MINIMUM" in output["professional_contract"]["blockers"]


def test_e9_is_sole_final_authority():
    output = harden_engine("E9", {
        "decision": "NO_TRADE",
        "reasons": ["SETUP_NOT_MATURE"],
    })
    assert output["master_authority"] == "SOLE_FINAL_AUTHORITY"
    assert output["professional_contract"]["decision_authority"] == "E9_ONLY"
    assert output["professional_contract"]["gate_state"] == "BLOCKED"
