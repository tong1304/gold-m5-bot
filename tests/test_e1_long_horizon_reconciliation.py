from production_v2.e1_brain import analyze_e1


def _bars_from_closes(closes, spread=0.25):
    bars = []
    previous = closes[0]
    for close in closes:
        bars.append({
            "open": previous,
            "high": max(previous, close) + spread,
            "low": min(previous, close) - spread,
            "close": close,
        })
        previous = close
    return bars


def test_coherent_slow_downtrend_is_not_erased_by_short_pullback():
    closes = [200.0 - 0.30 * i for i in range(90)]
    closes.extend([closes[-1] + 0.60 * i for i in range(1, 6)])
    result = analyze_e1(_bars_from_closes(closes))

    assert result["directional_pressure"] == "DOWN"
    assert result["market_state"] == "TREND_DOWN"
    assert result["trend_state"] == "DOWN"
    assert result["professional_reasoning"]["trend_confirmed"] is True
    assert result["professional_reasoning"]["trend_maturity"] in {"ESTABLISHED", "DEVELOPING"}
    assert result["trade_decision_authority"] is False
