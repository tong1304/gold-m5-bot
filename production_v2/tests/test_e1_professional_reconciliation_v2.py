from production_v2.e1_professional_layer import analyze_e1_professional


def _bars(n=100, direction=1.0):
    price = 100.0
    bars = []
    for i in range(n):
        drift = direction * (0.20 + (0.02 if i % 7 == 0 else 0.0))
        open_ = price
        close = price + drift
        high = max(open_, close) + 0.05
        low = min(open_, close) - 0.05
        bars.append({"open": open_, "high": high, "low": low, "close": close})
        price = close
    return bars


def test_e1_exposes_professional_contract():
    out = analyze_e1_professional(_bars())
    p = out["professional_reasoning"]
    assert out["e1_contract_version"] == "PROFESSIONAL_RECONCILED_V2"
    assert p["primary_thesis"]
    assert "counter_evidence" in p
    assert "protected_structure" in p
    assert "closed_candle_acceptance" in p
    assert "invalidation" in p
    assert "confidence" in p
    assert p["decision_boundary"].startswith("MARKET_STATE_ONLY")
    assert out["e1_trade_authority"] is False


def test_single_counter_candle_does_not_grant_trade_or_regime_authority():
    bars = _bars()
    last = bars[-1]
    last["open"], last["close"] = last["close"], last["open"]
    last["high"] = max(last["open"], last["close"]) + 0.05
    last["low"] = min(last["open"], last["close"]) - 0.05
    out = analyze_e1_professional(bars)
    p = out["professional_reasoning"]
    assert p["transition_confirmed"] is False or p["closed_candle_acceptance"]["confirmed"] is True
    assert out["e1_trade_authority"] is False


def test_insufficient_data_withholds_classification():
    out = analyze_e1_professional(_bars(40))
    assert out["market_state"] == "UNCLEAR"
    assert out["analysis_status"] == "INCOMPLETE"
