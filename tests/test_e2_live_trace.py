from production_v2.service import LiveService
from trading_system.engines import run_engine


def _uptrend_bars(n=100):
    bars = []
    for i in range(n):
        close = 3000.0 + i * 2.0
        bars.append({"open": close - 1.0, "high": close + 1.2, "low": close - 1.2, "close": close})
    return bars


def test_e2_live_trace_exposes_core_reasoning_without_subengines():
    result = run_engine("E2", {"bars": _uptrend_bars()}, {})
    trace = LiveService._reasoning(LiveService.__new__(LiveService), result)
    assert trace["role"] == "OPPORTUNITY_REGIME_ANALYST"
    assert trace["question"] == "What opportunity is the market offering right now?"
    assert trace["observations"]
    assert any(item.startswith("ema_gap_atr=") for item in trace["observations"])
    assert trace["reasons"]
