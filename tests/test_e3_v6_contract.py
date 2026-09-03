from production_v2.e3_brain import analyze_e3


def _bars(values):
    bars = []
    for i, close in enumerate(values):
        prev = values[i - 1] if i else close
        bars.append({
            "open": prev,
            "high": max(prev, close) + 0.4,
            "low": min(prev, close) - 0.4,
            "close": close,
        })
    return bars


def test_e3_exposes_current_causal_contract_without_trade_authority():
    result = analyze_e3(_bars([100 + i * 0.6 for i in range(80)]))
    assert result["analysis_status"] == "COMPLETE"
    assert result["architecture"] == "E3_PROFESSIONAL_MARKET_STRUCTURE_CAUSAL_V8"
    assert result["reasoning_role"] == "MARKET_STRUCTURE_ANALYST"
    assert result["specialists_active"] is False
    assert result["specialists_status"] == "PAUSED"
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["upstream_direction_used"] is False
    assert result["upstream_decisions_used"] is False
    assert result["upstream_gates_used"] is False
    assert result["score_used"] is False


def test_e3_separates_structural_state_from_count_state_and_slope():
    values = [100, 101, 99, 102, 100, 103, 101, 104, 102, 105] * 7
    result = analyze_e3(_bars(values))
    assert isinstance(result["external_structure"], dict)
    assert isinstance(result["internal_structure"], dict)
    assert result["external_structure"]["count_state"] == result["external_count_state"]
    assert result["internal_structure"]["count_state"] == result["internal_count_state"]
    assert result["reasoning_trace"]["slope_is_structural_authority"] is False
    assert result["decision"] is None
    assert result["gate"] is None


def test_e3_closed_break_requires_close_beyond_confirmed_structure():
    result = analyze_e3(_bars([100 + (i % 2) * 0.5 for i in range(80)]))
    assert result["bos"]["confirmed"] is False
    assert result["trade_decision_authority"] is False
