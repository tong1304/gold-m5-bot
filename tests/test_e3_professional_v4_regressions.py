from production_v2.e3_brain import analyze_e3


def _bars(values, wick=0.2):
    bars = []
    for i, close in enumerate(values):
        prev = values[i - 1] if i else close
        bars.append({
            "open": prev,
            "high": max(prev, close) + wick,
            "low": min(prev, close) - wick,
            "close": close,
        })
    return bars


def test_e3_never_uses_slope_as_structural_authority():
    values = [100, 101, 99, 102, 100, 103, 101, 104, 102, 105] * 6
    result = analyze_e3(_bars(values))
    assert result["upstream_direction_used"] is False
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["reasoning_trace"]["slope_is_structural_authority"] is False


def test_e3_exposes_external_and_internal_structure_separately():
    result = analyze_e3(_bars([100 + i * 0.4 for i in range(80)]))
    assert isinstance(result["external_structure"], dict)
    assert isinstance(result["internal_structure"], dict)
    assert "state" in result["external_structure"]
    assert "state" in result["internal_structure"]
    assert "basis" in result["external_structure"]
    assert "basis" in result["internal_structure"]


def test_e3_does_not_treat_wick_only_break_as_external_bos():
    values = [100 + (i % 2) * 0.5 for i in range(80)]
    values[-1] = 100.5
    bars = _bars(values)
    bars[-1]["high"] = 102.0
    result = analyze_e3(bars)
    assert result["bos"]["confirmed"] is False


def test_e3_preserves_e9_only_decision_authority():
    result = analyze_e3(_bars([100 + i * 0.6 for i in range(80)]))
    assert result["architecture"] == "E3_PROFESSIONAL_MARKET_STRUCTURE_CAUSAL_V8"
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["decision"] is None
    assert result["gate"] is None
