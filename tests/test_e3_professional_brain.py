from production_v2.e3_brain import analyze_e3


def bar(c, o=None, h=None, l=None):
    o = c if o is None else o
    h = max(c, o) + 0.2 if h is None else h
    l = min(c, o) - 0.2 if l is None else l
    return {"open": o, "high": h, "low": l, "close": c}


def test_e3_reports_complete_causal_contract():
    bars = [bar(100 + i * 0.2) for i in range(80)]
    result = analyze_e3(bars)
    assert result["analysis_status"] == "COMPLETE"
    assert result["architecture"] == "E3_PROFESSIONAL_MARKET_STRUCTURE_CAUSAL_V8"
    assert result["reasoning_role"] == "MARKET_STRUCTURE_ANALYST"
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["decision"] is None
    assert result["gate"] is None


def test_e3_uses_closed_confirmed_structure_only():
    bars = [bar(100 + i * 0.2) for i in range(80)]
    result = analyze_e3(bars)
    assert result["upstream_direction_used"] is False
    assert result["upstream_decisions_used"] is False
    assert result["upstream_gates_used"] is False
    assert result["trade_decision_authority"] is False
    assert result["reasoning_trace"]["slope_is_structural_authority"] is False


def test_e3_distinguishes_external_and_internal_structure():
    bars = [bar(100 + i * 0.2) for i in range(80)]
    result = analyze_e3(bars)
    assert isinstance(result["external_structure"], dict)
    assert isinstance(result["internal_structure"], dict)
    assert result["external_structure"]["basis"] == "ORDERED_CONFIRMED_SWINGS"
    assert result["internal_structure"]["basis"] == "ORDERED_CONFIRMED_SWINGS"


def test_e3_never_treats_wick_only_move_as_closed_break():
    bars = [bar(100 + (i % 2) * 0.5) for i in range(80)]
    bars[-1]["high"] = 102.0
    result = analyze_e3(bars)
    assert result["bos"]["confirmed"] is False


def test_e3_structure_does_not_inherit_trade_authority_from_inputs():
    bars = [bar(100 + i * 0.2) for i in range(80)]
    baseline = analyze_e3(bars)
    contaminated = analyze_e3(
        bars,
        E1_result={"direction": "DOWN"},
        E2_result={"direction": "DOWN"},
    )
    assert baseline["direction"] == contaminated["direction"]
    assert contaminated["upstream_direction_used"] is False
    assert contaminated["upstream_decisions_used"] is False
    assert contaminated["upstream_gates_used"] is False
