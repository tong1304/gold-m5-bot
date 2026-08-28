from production_v2.e1_professional_layer_v4 import analyze_e1_professional_v4


def _bars(direction: str, n: int = 100):
    bars = []
    price = 100.0
    for i in range(n):
        drift = 1.0 if direction == "up" else -1.0
        close = price + drift
        bars.append({"open": price, "high": max(price, close) + 0.2, "low": min(price, close) - 0.2, "close": close})
        price = close
    return bars


def test_v4_contract_is_market_state_only():
    result = analyze_e1_professional_v4(_bars("up"))
    assert result["e1_trade_authority"] is False
    assert result["trade_decision_authority"] is False
    assert "state_machine" in result["professional_reasoning"]
    assert result["e1_contract_version"] == "PROFESSIONAL_STATE_MACHINE_V4"


def test_transition_status_has_explicit_levels():
    result = analyze_e1_professional_v4(_bars("up"))
    sm = result["professional_reasoning"]["state_machine"]
    assert sm["levels"] == ["NONE", "DETECTED", "WATCH", "VALIDATED", "COMMITTED"]
    assert sm["transition_status"] in sm["levels"]


def test_insufficient_data_withholds_classification():
    result = analyze_e1_professional_v4(_bars("up", 20))
    assert result["market_state"] == "UNCLEAR"
    assert result["analysis_status"] == "INCOMPLETE"


def test_no_transition_does_not_claim_commit():
    result = analyze_e1_professional_v4(_bars("up"))
    assert result["transition_committed"] is False or result["transition_status"] == "COMMITTED"
    if result["transition_status"] != "COMMITTED":
        assert result["transition_validated"] is False
