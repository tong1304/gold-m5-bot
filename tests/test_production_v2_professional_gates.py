from production_v2.engines import _professional_gate


def test_e1_neutral_market_state_is_not_an_immediate_failure():
    output = {
        "1A": {"state": "VALID"},
        "1C": {"direction": "NEUTRAL"},
        "1D": {"state": "RANGE"},
        "1G": {"state": "STABLE"},
    }
    passed, reasons = _professional_gate("E1", output, {})
    assert passed is True
    assert reasons == ()


def test_e2_range_regime_does_not_require_directional_bias():
    output = {
        "1C": {"direction": "NEUTRAL"},
        "2B": {"regime": "RANGE"},
        "2F": {"regime": "STABLE"},
    }
    passed, reasons = _professional_gate("E2", output, {})
    assert passed is True
    assert reasons == ()


def test_e3_bos_is_evidence_not_a_universal_gate():
    output = {
        "3B": {"state": "BULLISH"},
        "3C": {"state": "NO_BOS"},
        "3F": {"state": "INTERNAL_EXTERNAL_MIXED"},
    }
    passed, reasons = _professional_gate("E3", output, {})
    assert passed is True
    assert reasons == ()


def test_e4_does_not_require_sweep_for_every_setup():
    output = {
        "4A": {"state": "LIQUIDITY_ZONE"},
        "4B": {"state": "NO_SWEEP"},
        "4C": {"state": "NO_REJECTION"},
        "4D": {"state": "ACCEPTANCE"},
        "4F": {"state": "QUALITY_MEASURABLE"},
    }
    passed, reasons = _professional_gate("E4", output, {})
    assert passed is True
    assert reasons == ()


def test_e5_extended_location_is_a_hard_disadvantage():
    output = {
        "5D": {"state": "EXTENDED"},
        "5E": {"state": "SPACE_AVAILABLE"},
        "5F": {"state": "LOCATION_QUALITY_MEASURABLE"},
    }
    passed, reasons = _professional_gate("E5", output, {})
    assert passed is False
    assert "E5_LOCATION_DISADVANTAGED" in reasons


def test_e8_uses_configured_minimum_rr_instead_of_hardcoded_two_r():
    output = {
        "8G": {"state": "RISK_GATE_READY"},
        "trade_plan": {"valid": True, "rr_tp2": 1.5},
    }
    passed, reasons = _professional_gate("E8", output, {"risk_policy": {"min_rr": 1.3}})
    assert passed is True
    assert reasons == ()


def test_e8_rejects_rr_below_configured_minimum():
    output = {
        "8G": {"state": "RISK_GATE_READY"},
        "trade_plan": {"valid": True, "rr_tp2": 1.2},
    }
    passed, reasons = _professional_gate("E8", output, {"risk_policy": {"min_rr": 1.3}})
    assert passed is False
    assert "E8_RR_BELOW_MINIMUM" in reasons
