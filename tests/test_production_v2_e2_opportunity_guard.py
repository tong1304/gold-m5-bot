from production_v2.engines import run_engine


def _steady_trend_bars(n=100):
    bars = []
    for i in range(n):
        close = 3000.0 + i * 1.5
        bars.append({"open": close - 0.8, "high": close + 1.0, "low": close - 1.0, "close": close})
    return bars


def test_production_v2_e2_requires_a_real_setup_before_naming_an_opportunity():
    """Trend direction alone must not become TREND_CONTINUATION/PULLBACK."""
    out = run_engine("E2", {"bars": _steady_trend_bars()}, {}).output

    assert out["direction"] == "UP"
    assert out["opportunity"] == "WAIT_FOR_REPRICING"
    assert out["opportunity_decision"] == "WAIT"
    assert "OPPORTUNITY_THESIS_ESTABLISHED" not in out["reason_codes"]
    assert "clear directional commitment / repricing" in out["missing_evidence"]
