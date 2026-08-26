from production_v2.engines import run_engine


def _bars(direction="down", n=80):
    bars=[]
    price=100.0
    for i in range(n):
        step=-0.45 if direction == "down" else 0.45
        close=price + step
        high=max(price, close)+0.08
        low=min(price, close)-0.08
        bars.append({"open":price,"high":high,"low":low,"close":close,"volume":1000,"timestamp":i})
        price=close
    return bars


def test_e1_reports_market_state_without_trade_direction_or_authority():
    result=run_engine("E1", {"symbol":"XAU/USD","timeframe":"M5","bars":_bars("down")})
    out=result.output
    assert out["decision_authority"] == "E9_ONLY"
    assert out["market_state"] in {"TREND_DOWN", "EXPANSION", "TRANSITION", "UNCLEAR"}
    assert out["directional_pressure"] in {"BEARISH", "BULLISH", "BALANCED"}
    assert "decision" not in out
    assert out["trade_decision_authority"] is False
    assert isinstance(out["evidence"], list)
    assert isinstance(out["conflicts"], list)
    assert isinstance(out["reasoning_trace"], list)


def test_e1_can_admit_unclear_instead_of_forcing_direction():
    bars=[]
    price=100.0
    for i in range(80):
        close=price + (0.2 if i % 2 else -0.2)
        bars.append({"open":price,"high":max(price,close)+0.05,"low":min(price,close)-0.05,"close":close,"volume":1000,"timestamp":i})
        price=close
    result=run_engine("E1", {"symbol":"BTC/USD","timeframe":"M5","bars":bars})
    out=result.output
    assert out["directional_pressure"] == "BALANCED"
    assert out["market_state"] in {"RANGE", "COMPRESSION", "TRANSITION", "UNCLEAR"}


def test_e1_brain_exposes_professional_question_and_decision_independent_reasoning():
    result=run_engine("E1", {"symbol":"XAU/USD","timeframe":"M5","bars":_bars("down")})
    out=result.output
    assert out["question"] == "What is the market doing right now?"
    assert out["reasoning_role"] == "MARKET_STATE_ANALYST"
    assert out["analysis_status"] == "COMPLETE"
    assert out["decision_authority"] == "E9_ONLY"
    assert out["professional_reasoning"]["directional_pressure"] == out["directional_pressure"]
    assert out["professional_reasoning"]["market_state"] == out["market_state"]
    assert out["professional_reasoning"]["confidence"] == out["confidence"]
    assert out["professional_reasoning"]["next_question"] in {
        "IS_THIS_STATE_STABLE_OR_TRANSITIONING?",
        "IS_DIRECTIONAL_PRESSURE_STRONG_ENOUGH_TO_MATTER?",
        "IS_MARKET_TOO_BALANCED_TO_CLASSIFY?",
    }
