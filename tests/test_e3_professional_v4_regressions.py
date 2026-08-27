from production_v2.e3_brain import analyze_e3


def _bar(close, open_=100.0, high=None, low=None):
    high = max(open_, close) if high is None else high
    low = min(open_, close) if low is None else low
    return {"open": open_, "high": high, "low": low, "close": close}


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
    # Price trends upward, but the confirmed swing structure is deliberately
    # conflicting. E3 must report the structural conflict rather than invent
    # a bullish structure from a regression/slope alone.
    values = [100, 101, 99, 102, 100, 103, 101, 104, 102, 105] * 6
    result = analyze_e3(_bars(values))
    assert result["upstream_direction_used"] is False
    assert result["decision"] is None
    assert result["gate"] is None
    assert "slope_context" in " ".join(result["observations"])
    assert result["structure_state"] in {
        "TRANSITION",
        "DIRECTIONAL_CONTEXT_UNCONFIRMED",
        "CONTINUATION",
        "DEVELOPING_STRUCTURE",
        "INTERNAL_CONFLICT",
        "INTERNAL_COUNTER_MOVE",
        "BREAKOUT_CONFIRMED",
        "CHANGE_OF_CHARACTER",
        "STRUCTURE_FAILURE",
        "RANGE_OR_UNCLEAR",
    }


def test_e3_exposes_external_and_internal_structure_separately():
    result = analyze_e3(_bars([100 + i * 0.4 for i in range(80)]))
    assert "external_structure" in result
    assert "internal_structure" in result
    assert "external_structure" in result["observations"][-20:][0] or any(
        x.startswith("external_structure=") for x in result["observations"]
    )
    assert any(x.startswith("internal_structure=") for x in result["observations"])


def test_e3_does_not_treat_wick_only_break_as_external_bos():
    # A wick can take liquidity, but without a close beyond the level it is not
    # a confirmed structural break.
    values = [100 + (i % 2) * 0.5 for i in range(80)]
    values[-1] = 100.5
    bars = _bars(values)
    bars[-1]["high"] = 102.0
    result = analyze_e3(bars)
    assert result["external_structure"]
    assert result["bos"]["confirmed"] is False


def test_e3_preserves_e9_only_decision_authority():
    result = analyze_e3(_bars([100 + i * 0.6 for i in range(80)]))
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["decision"] is None
    assert result["gate"] is None
