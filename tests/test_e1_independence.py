from production_v2.engines import run_engine


def _bars(direction="down", n=80):
    bars=[]
    price=100.0
    step=-0.45 if direction == "down" else 0.45
    for i in range(n):
        close=price+step
        bars.append({"open":price,"high":max(price,close)+0.08,"low":min(price,close)-0.08,"close":close,"timestamp":i})
        price=close
    return bars


def test_e1_is_independent_of_subengine_and_peer_evidence():
    snapshot={"symbol":"XAU/USD","timeframe":"M5","bars":_bars("down")}
    hostile_bus={
        "E2":{"engine_id":"E2","evidence":{"2A":{"output":{"direction":"UP","state":"TREND"}}}},
        "E3":{"engine_id":"E3","evidence":{"3A":{"output":{"direction":"UP","structure":"BULLISH"}}}},
    }
    result=run_engine("E1",snapshot,hostile_bus)
    out=result.output
    assert out["sub_engines_enabled"] is False
    assert out["specialists"] == {}
    assert out["peer_evidence_count"] == 0
    assert out["upstream_decisions_used"] is False
    assert out["upstream_gates_used"] is False
    assert out["score_used"] is False
    assert out["market_state"] == "TREND_DOWN"
    assert out["directional_pressure"] == "BEARISH"


def test_e1_professional_reasoning_contains_independent_evidence_and_consensus():
    out=run_engine("E1",{"symbol":"XAU/USD","timeframe":"M5","bars":_bars("down")}).output
    reasoning=out["professional_reasoning"]
    assert reasoning["task"] == "DESCRIBE_MARKET_STATE_ONLY"
    assert "independent_evidence" in reasoning
    assert "directional_consensus" in reasoning
    assert reasoning["independent_evidence"]["structure"] in {"BEARISH","MIXED"}
    assert reasoning["directional_consensus"]["confirmed"] in {True,False}
