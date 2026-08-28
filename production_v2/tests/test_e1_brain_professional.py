from production_v2.e1_brain import analyze_e1


def bars_from_closes(closes):
    bars=[]
    for i,c in enumerate(closes):
        prev=closes[i-1] if i else c
        span=max(0.2, abs(c-prev)*0.35)
        bars.append({"open":prev,"high":max(prev,c)+span,"low":min(prev,c)-span,"close":c})
    return bars


def test_insufficient_data_withholds_state():
    out=analyze_e1(bars_from_closes([100+i for i in range(20)]))
    assert out["market_state"]=="UNCLEAR"
    assert out["analysis_status"]=="INCOMPLETE"
    assert out["trade_decision_authority"] is False


def test_strong_directional_structure_is_trend_not_just_pressure():
    closes=[]
    price=100.0
    for i in range(100):
        price += 0.8 if i < 80 else 0.45
        closes.append(price)
    out=analyze_e1(bars_from_closes(closes))
    assert out["market_state"] in {"TREND_UP","EXPANSION"}
    assert out["directional_pressure"]=="UP"
    assert out["professional_reasoning"]["task"]=="DESCRIBE_MARKET_STATE_ONLY"


def test_range_requires_non_directional_behavior():
    closes=[]
    for i in range(100):
        closes.append(100 + (1.5 if i%4 in (0,1) else -1.5))
    out=analyze_e1(bars_from_closes(closes))
    assert out["market_state"] in {"RANGE","COMPRESSION","UNCLEAR"}
    assert out["market_state"] not in {"TREND_UP","TREND_DOWN"}


def test_output_exposes_counter_evidence_conflict_stability_and_invalidation():
    closes=[100 + 0.55*i for i in range(70)] + [138 - 0.75*i for i in range(30)]
    out=analyze_e1(bars_from_closes(closes))
    pr=out["professional_reasoning"]
    assert "counter_evidence" in pr
    assert "state_stability" in pr
    assert "invalidation" in pr
    assert "independent_evidence" in pr
