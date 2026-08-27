from production_v2.e2_brain import analyze_e2


def _monotonic_down_snapshot(n=200):
    bars = []
    price = 3000.0
    for i in range(n):
        close = price - 2.0
        bars.append({
            "open": price,
            "high": price + 0.25,
            "low": close - 0.25,
            "close": close,
        })
        price = close
    return {"bars": bars}


def test_e2_does_not_call_a_bare_trend_into_a_pullback_opportunity():
    result = analyze_e2(_monotonic_down_snapshot())

    assert result["direction"] == "DOWN"
    assert result["opportunity"] == "WAIT_FOR_REPRICING"
    assert result["phase"] == "TRANSITION"
    assert result["opportunity_state"] == "WAIT"
    assert result["opportunity_decision"] == "WAIT"
    assert result["opportunity_score"] == 0.0
    assert result["entry"] is None
