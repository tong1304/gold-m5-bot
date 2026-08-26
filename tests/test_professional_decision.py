from v11.professional_decision import wrap


def _base_result():
    return {
        "engine_version": "LEGACY-TEST",
        "signal": "BUY",
        "strategy": "TEST_SETUP",
        "regime": {"m5_regime": "TREND_UP"},
        "data_quality": {"m5": [], "m15": [], "h1": []},
        "selected_setup": {
            "status": "PASS",
            "quality": 90,
            "trigger_signature": "TRIGGER-1",
            "entry_type_hint": "MARKET",
            "evidence": {
                "choch_index": 10,
                "sweep_index": 11,
                "zone": {"low": 1, "high": 2},
            },
        },
        "setup_score": {"score": 90},
        "trigger_id": "TRIGGER-1",
        "entry_type": "MARKET",
        "trade_levels": {"valid": True, "risk_reward": 2.0, "minimum_rr": 1.5},
        "rejection_reasons": [],
    }


def test_e9_can_authorize_only_when_all_evidence_layers_exist():
    result = wrap(lambda **_: _base_result(), legacy_engine_version="LEGACY-TEST")(None)
    assert result["signal"] == "BUY"
    assert result["decision_authority"] == "E9"
    assert result["professional_decision"]["e9"]["execution_eligible"] is True
    assert result["legacy_engine_version"] == "LEGACY-TEST"


def test_missing_specialist_evidence_forces_no_trade():
    def legacy(**_):
        result = _base_result()
        result["selected_setup"]["evidence"].pop("sweep_index")
        return result

    result = wrap(legacy, legacy_engine_version="LEGACY-TEST")(None)
    assert result["signal"] == "NO_TRADE"
    assert result["professional_decision"]["e9"]["execution_eligible"] is False
    assert any("E4:LIQUIDITY_EVIDENCE_UNAVAILABLE" in x for x in result["professional_decision"]["hard_failures"])
