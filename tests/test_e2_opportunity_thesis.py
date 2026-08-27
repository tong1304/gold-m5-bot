from trading_system.engines import run_engine


def _trend_bars(n=100):
    bars = []
    price = 3000.0
    for i in range(n):
        close = price + i * 1.5
        bars.append({"open": close - 0.8, "high": close + 1.0, "low": close - 1.0, "close": close})
    return bars


def test_e2_keeps_directional_opportunity_thesis_separate_from_confirmation():
    out = run_engine("E2", {"bars": _trend_bars()}, {}).output

    assert out["architecture"] == "E2_PROFESSIONAL_CORE_ONLY"
    assert out["trade_decision_authority"] == "E9_ONLY"
    assert out["entry"] is None
    assert out["trigger"] is None
    assert out["risk"] is None
    assert out["gate"] is None

    if out["regime"] == "TREND" and out["direction"] in {"UP", "DOWN"}:
        assert out["opportunity"] in {"TREND_PULLBACK_CONTINUATION", "TREND_CONTINUATION"}
        assert out["opportunity_state"] in {"DEVELOPING", "CONTEXT_READY"}
        assert out["opportunity_decision"] in {"WATCH", "ACTIONABLE_BIAS"}
        assert out["professional_reasoning"]["entry_authorized"] is False
