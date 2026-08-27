from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6
from production_v2.e7_brain import analyze_e7


def _bars(n=60):
    bars=[]
    price=100.0
    for i in range(n):
        close=price-0.15 if i >= n-12 else price+0.05
        bars.append({"open": price, "high": max(price, close)+0.4, "low": min(price, close)-0.4, "close": close})
        price=close
    return bars


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, None, 70.0, output, ())


def test_e6_preserves_e2_thesis_when_structure_is_mixed():
    upstream = {
        "E1": _engine("E1", {"market_state": "TRANSITION", "directional_pressure": "DOWN"}),
        "E2": _engine("E2", {
            "direction": "SELL",
            "opportunity": "TREND_PULLBACK_CONTINUATION",
            "phase": "DEVELOPING",
            "thesis": "TREND/DOWN creates TREND_PULLBACK_CONTINUATION",
        }),
        "E3": _engine("E3", {
            "finding": "MIXED_STRUCTURE",
            "external_count_state": "DOWN",
            "internal_count_state": "MIXED",
            "slope_context": "DOWN",
        }),
        "E4": _engine("E4", {"finding": "NO_CONFIRMED_LIQUIDITY_EVENT"}),
        "E5": _engine("E5", {"finding": "SPACE_CONSTRAINED"}),
    }
    result = analyze_e6({"bars": _bars()}, upstream)
    assert result.output["direction"] == "SELL"
    assert result.output["setup"] == "TREND_PULLBACK_CONTINUATION"
    assert result.output["maturity"] == "DEVELOPING"
    assert result.output["thesis"] == "SELL_TREND_PULLBACK_CONTINUATION"
    assert "STRUCTURE_MIXED" in result.output["counter_evidence"]
    assert result.gate_passed is False


def test_e7_reports_missing_trigger_instead_of_claiming_valid_trigger():
    upstream = {
        "E6": _engine("E6", {
            "direction": "SELL",
            "setup": "TREND_PULLBACK_CONTINUATION",
            "maturity": "DEVELOPING",
        }),
        "E4": _engine("E4", {"finding": "NO_CONFIRMED_LIQUIDITY_EVENT"}),
    }
    result = analyze_e7({"bars": _bars()}, upstream)
    assert result.output["confirmation"] == "DEVELOPING"
    assert result.output["trigger_status"] == "NOT_CONFIRMED"
    assert "VALID_CLOSED_CANDLE_TRIGGER" in result.output["missing_evidence"]
    assert result.gate_passed is False
