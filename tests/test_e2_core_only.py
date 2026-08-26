from trading_system.engines import run_engine


def _bars(n=80):
    bars = []
    price = 3000.0
    for i in range(n):
        close = price - i * 1.5
        bars.append({"open": close + 0.5, "high": close + 1.0, "low": close - 1.0, "close": close})
    return bars


def _uptrend_bars(n=100):
    bars = []
    price = 3000.0
    for i in range(n):
        close = price + i * 2.0
        bars.append({"open": close - 1.0, "high": close + 1.2, "low": close - 1.2, "close": close})
    return bars


def _transition_bars(n=100):
    bars = []
    price = 3000.0
    for i in range(n):
        # Old downtrend remains in the longer EMA, while the recent impulse
        # turns upward. A professional E2 should treat this as repricing/transition,
        # not force a tradeable trend from a single moving-average crossover.
        if i < n - 12:
            close = price - i * 1.8
        else:
            close = price - (n - 12) * 1.8 + (i - (n - 12)) * 7.0
        bars.append({"open": close - 0.2, "high": close + 1.5, "low": close - 1.5, "close": close})
    return bars


def test_e2_uses_core_brain_without_running_subengines():
    e1 = {
        "engine_id": "E1",
        "evidence": {"output": {"directional_pressure": "BEARISH", "market_state": "TREND_DOWN", "confidence": 0.9}},
        "reason_codes": [],
    }
    result = run_engine("E2", {"bars": _bars()}, {"E1": e1})
    assert result.engine_id == "E2"
    assert result.output["architecture"] == "E2_PROFESSIONAL_CORE_ONLY"
    assert result.output["sub_engines_active"] is False
    assert result.output["specialists"] == {}
    assert result.output["direction"] in {"UP", "DOWN", "NEUTRAL"}
    assert result.output["decision"] is None
    assert result.output["gate"] is None


def test_e2_does_not_convert_market_thesis_into_trade_decision():
    result = run_engine("E2", {"bars": _bars()}, {})
    assert result.output["decision"] is None
    assert result.output["entry"] is None
    assert result.output["trigger"] is None
    assert result.output["risk"] is None
    assert result.output["gate"] is None


def test_e2_professional_brain_publishes_a_complete_independent_thesis():
    result = run_engine("E2", {"bars": _uptrend_bars()}, {})
    output = result.output
    assert output["regime"] == "TREND"
    assert output["direction"] == "UP"
    assert output["opportunity"] == "TREND_CONTINUATION"
    assert output["opportunity_state"] in {"ACTIONABLE_CONTEXT", "DEVELOPING"}
    assert output["professional_reasoning"]["question"] == "What opportunity is the market offering right now?"
    assert output["professional_reasoning"]["evidence"]
    assert output["professional_reasoning"]["missing_evidence"] == []
    assert output["professional_reasoning"]["counter_evidence"] == []


def test_e2_does_not_turn_old_ema_bias_into_a_false_trend_during_repricing():
    result = run_engine("E2", {"bars": _transition_bars()}, {})
    output = result.output
    assert output["regime"] in {"TRANSITION", "BREAKOUT"}
    if output["regime"] == "TRANSITION":
        assert output["direction"] == "NEUTRAL"
        assert output["opportunity"] == "WAIT_FOR_REPRICING"
        assert output["opportunity_state"] == "WAIT"


def test_e2_e1_is_only_cross_check_not_a_direction_override():
    bearish_e1 = {
        "engine_id": "E1",
        "evidence": {"output": {"directional_pressure": "BEARISH", "market_state": "TREND_DOWN", "structure": "BEARISH"}},
        "reason_codes": [],
    }
    result = run_engine("E2", {"bars": _uptrend_bars()}, {"E1": bearish_e1})
    output = result.output
    assert output["direction"] == "UP"
    assert output["alignment_with_e1"] == "CONFLICT"
    assert output["professional_reasoning"]["reasoning_mode"] == "INDEPENDENT_E2_THESIS_FIRST"
