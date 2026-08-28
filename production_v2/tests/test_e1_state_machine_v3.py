from production_v2.e1_professional_layer_v3 import analyze_e1_professional_v3


def _bars(directions, start=100.0):
    bars = []
    price = start
    for i, direction in enumerate(directions):
        if direction == "UP":
            close = price + 1.0
        elif direction == "DOWN":
            close = price - 1.0
        else:
            close = price
        high = max(price, close) + 0.25
        low = min(price, close) - 0.25
        bars.append({"open": price, "high": high, "low": low, "close": close, "time": i})
        price = close
    return bars


def test_e1_v3_exposes_state_machine_contract():
    result = analyze_e1_professional_v3(_bars(["UP"] * 80 + ["DOWN"] * 2))
    professional = result["professional_reasoning"]
    assert "state_machine" in professional
    assert "previous_regime" in professional["state_machine"]
    assert "current_regime" in professional["state_machine"]
    assert "transition_status" in professional["state_machine"]
    assert "persistence" in professional
    assert "invalidation" in professional


def test_e1_v3_does_not_commit_transition_on_single_counter_candle():
    result = analyze_e1_professional_v3(_bars(["UP"] * 80 + ["DOWN"]))
    sm = result["professional_reasoning"]["state_machine"]
    assert sm["transition_status"] != "COMMITTED"
    assert result["professional_reasoning"]["counter_evidence_severity"] in {"NONE", "LOW"}


def test_e1_v3_never_has_trade_authority():
    result = analyze_e1_professional_v3(_bars(["UP"] * 90))
    assert result["trade_decision_authority"] is False
    assert result["e1_trade_authority"] is False
