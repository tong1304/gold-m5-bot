from trading_system.engines import run_engine


def _bars(n=80):
    bars = []
    price = 3000.0
    for i in range(n):
        close = price - i * 1.5
        bars.append({"open": close + 0.5, "high": close + 1.0, "low": close - 1.0, "close": close})
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
