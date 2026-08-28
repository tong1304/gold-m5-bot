from math import sin

from production_v2.e1_brain import analyze_e1


def _bars_from_closes(closes):
    bars = []
    for i, close in enumerate(closes):
        prev = closes[i - 1] if i else close
        high = max(prev, close) + 0.35
        low = min(prev, close) - 0.35
        bars.append({"open": prev, "high": high, "low": low, "close": close})
    return bars


def _bearish_impulse_with_long_horizon_conflict():
    closes = []
    price = 100.0
    for i in range(80):
        price += 0.10 if i < 55 else -1.10
        closes.append(price)
    return _bars_from_closes(closes)


def _clean_bear_trend():
    closes = [200.0 - 0.55 * i + 0.90 * sin(i * 0.70) for i in range(100)]
    return _bars_from_closes(closes)


def test_e1_calls_recent_bearish_impulse_a_transition_when_horizons_conflict():
    result = analyze_e1(_bearish_impulse_with_long_horizon_conflict())
    assert result["directional_pressure"] == "DOWN"
    assert result["market_state"] == "TRANSITION"
    assert "SHORT_VS_LONG_HORIZON" in result["conflicts"]
    assert result["professional_reasoning"]["task"] == "DESCRIBE_MARKET_STATE_ONLY"
    assert result["trade_decision_authority"] is False


def test_e1_requires_structure_and_price_alignment_before_declaring_trend():
    result = analyze_e1(_clean_bear_trend())
    assert result["market_state"] == "TREND_DOWN"
    assert result["directional_pressure"] == "DOWN"
    assert result["professional_reasoning"]["trend_confirmed"] is True


def test_e1_never_exports_setup_or_execution_decisions():
    result = analyze_e1(_clean_bear_trend())
    forbidden_top_level = {"decision", "entry", "stop", "target", "position_size", "execution"}
    assert not forbidden_top_level.intersection(result.keys())
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
