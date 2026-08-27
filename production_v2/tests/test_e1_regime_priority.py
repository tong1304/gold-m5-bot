from production_v2.e1_brain import analyze_e1


def bearish_impulse_with_bullish_ema_lag(n=120):
    """Closed candles with persistent bearish pressure while EMA20 still lags above EMA50."""
    out = []
    price = 100.0
    for i in range(n):
        step = 0.10 if i < 105 else -0.20
        close = price + step
        out.append({"open": price, "high": max(price, close) + 0.05, "low": min(price, close) - 0.05, "close": close})
        price = close
    return out


def test_persistent_bearish_pressure_with_ema_lag_is_transition_not_compression():
    result = analyze_e1(bearish_impulse_with_bullish_ema_lag())

    assert result["directional_pressure"] == "DOWN"
    assert result["market_state"] == "TRANSITION"
    assert result["transition"] == "PRESENT"
    assert "EMA_VS_PRICE_PRESSURE" in result["conflicts"]
