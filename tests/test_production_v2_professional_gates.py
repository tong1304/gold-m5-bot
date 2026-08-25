from production_v2.engines import run_engine


def _bars(direction="DOWN", body_ratio=0.70, count=30):
    bars = []
    price = 100.0
    for i in range(count):
        if direction == "DOWN":
            close = price - 0.8
        else:
            close = price + 0.8
        body = abs(close - price)
        span = body / body_ratio if body_ratio else 3.0
        high = max(price, close) + (span - body) / 2
        low = min(price, close) - (span - body) / 2
        bars.append({"open": price, "high": high, "low": low, "close": close})
        price = close
    return bars


def test_e7_weak_confirmation_is_not_a_pass():
    result = run_engine("E7", {"symbol": "BTC/USD", "timeframe": "M5", "bars": _bars(body_ratio=0.2582)})
    assert result.gate_passed is False
    assert "E7_CONFIRMATION_INSUFFICIENT" in result.reason_codes


def test_e6_developing_setup_is_not_trade_ready():
    result = run_engine("E6", {"symbol": "BTC/USD", "timeframe": "M5", "bars": _bars(body_ratio=0.2582)})
    assert result.gate_passed is False
    assert "E6_SETUP_NOT_MATURE" in result.reason_codes


def test_e3_requires_directional_structure_evidence():
    result = run_engine("E3", {"symbol": "BTC/USD", "timeframe": "M5", "bars": _bars(direction="DOWN")})
    assert result.gate_passed is False
    assert "E3_STRUCTURE_NOT_CONFIRMED" in result.reason_codes
