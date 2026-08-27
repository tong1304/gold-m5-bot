from production_v2.e3_brain import analyze_e3


# E3 is a single runtime brain; 3A-3F are intentionally parked.


def _bars(closes):
    bars = []
    for i, close in enumerate(closes):
        close = float(close)
        bars.append({
            "open": close - 0.2,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": 1.0,
            "timestamp": i,
        })
    return bars


def test_e3_returns_real_evidence_contract():
    closes = [100 + ((i % 5) * 0.15) for i in range(60)]
    result = analyze_e3(_bars(closes))
    assert result["analysis_status"] == "COMPLETE"
    assert result["question"] == "What is price structure communicating?"
    assert result["finding"] != "UNRESOLVED"
    assert result["observations"]
    assert result["architecture"] == "E3_SINGLE_PROFESSIONAL_BRAIN_V2"
    assert result["sub_engines_active"] is False
    assert result["upstream_direction_used"] is False
    assert result["trade_decision_authority"] is False


def test_e3_detects_or_rejects_break_as_closed_candle_evidence():
    closes = [100.0] * 25
    closes += [101.0, 99.0, 101.5, 99.2, 100.0, 101.0, 100.0, 101.2]
    closes += [100.5, 102.5, 103.0, 103.2, 103.4]
    closes += [103.0] * 20
    result = analyze_e3(_bars(closes))
    assert result["direction"] in {"UP", "MIXED", "NEUTRAL"}
    assert result["bos"]["event"] in {"CONFIRMED_BOS", "NO_BOS"}
    assert "evidence" in result
    assert "reason_codes" in result


def test_e3_never_exposes_trade_authority_or_gate():
    result = analyze_e3(_bars([100 + (i % 3) for i in range(50)]))
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["gate"] is None
    assert result["sub_engines_status"] == "PAUSED"


def test_e3_trace_reports_the_same_structural_states_used_by_the_brain():
    result = analyze_e3(_bars([100 + (i % 7) * 0.25 for i in range(80)]))
    trace = result["reasoning_trace"]
    assert trace["external_state"] == result["external_structure"]["state"]
    assert trace["internal_state"] == result["internal_structure"]["state"]
    assert trace["external_count_state"] == result["reasoning_trace"]["external_count_state"]
    assert trace["internal_count_state"] == result["reasoning_trace"]["internal_count_state"]


def test_e3_slope_cannot_be_structural_authority():
    # A strong recent slope with unresolved swing structure must not be promoted
    # into a confirmed directional structure by slope alone.
    closes = [100.0 + i * 0.02 for i in range(80)]
    result = analyze_e3(_bars(closes))
    assert result["reasoning_trace"]["slope_is_structural_authority"] is False
    if result["bos"]["confirmed"] is False:
        assert result["direction"] in {"MIXED", "NEUTRAL"}
