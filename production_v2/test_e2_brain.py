from __future__ import annotations

from production_v2.e2_brain import analyze_e2


def _bars(n: int = 80):
    bars = []
    price = 100.0
    for i in range(n):
        open_ = price
        close = price - 0.35 if i > 5 else price
        high = max(open_, close) + 0.08
        low = min(open_, close) - 0.08
        bars.append({"open": open_, "high": high, "low": low, "close": close})
        price = close
    return bars


def test_e2_emits_professional_reasoning_and_real_conclusion():
    result = analyze_e2({"bars": _bars(), "E1_result": {"directional_pressure": "BEARISH", "market_state": "TREND_DOWN"}})
    reasoning = result.get("professional_reasoning") or {}
    assert result["reasoning_mode"] == "SINGLE_PROFESSIONAL_CORE"
    assert result["sub_engines_active"] is False
    assert result["question"] == "What opportunity is the market offering right now?"
    assert reasoning.get("question") == result["question"]
    assert reasoning.get("conclusion") not in (None, "", "UNRESOLVED")
    assert result.get("direction") in {"UP", "DOWN", "NEUTRAL"}
    assert result.get("regime") in {"TREND", "BREAKOUT", "MEAN_REVERSION", "RANGE", "TRANSITION"}


def test_e2_does_not_delegate_thesis_to_e1():
    bars = _bars()
    own = analyze_e2({"bars": bars, "E1_result": {"directional_pressure": "BULLISH", "market_state": "TREND_UP"}})
    no_e1 = analyze_e2({"bars": bars})
    assert own["regime"] == no_e1["regime"]
    assert own["direction"] == no_e1["direction"]
    assert own["independence"] == "E2_FIRST_E1_CROSS_CHECK"
