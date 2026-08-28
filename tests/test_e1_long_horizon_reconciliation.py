from production_v2.e1_brain import analyze_e1


def _bars_from_closes(closes, spread=0.10):
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


def _slow_downtrend_with_noisy_pullback():
    closes = [200.0 - 0.25 * i for i in range(60)]
    for i in range(30):
        closes.append(closes[-1] + (1.0 if i % 2 == 0 else -1.2))
    closes.extend([closes[-1] - 0.2] * 5)
    closes.extend([closes[-1] + 0.2] * 5)
    return closes


def test_coherent_slow_downtrend_is_not_erased_by_noisy_short_pullback():
    result = analyze_e1(_bars_from_closes(_slow_downtrend_with_noisy_pullback()))

    assert result["directional_pressure"] == "DOWN"
    assert result["market_state"] == "TREND_DOWN"
    assert result["trend_state"] == "DOWN"
    assert result["professional_reasoning"]["trend_confirmed"] is True
    assert result["professional_reasoning"]["trend_maturity"] == "DEVELOPING"
    assert result["professional_reasoning"]["ownership_boundaries"]["does_not_own"]
    assert result["trade_decision_authority"] is False
