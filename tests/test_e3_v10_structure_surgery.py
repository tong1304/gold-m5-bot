from production_v2.e3_brain import analyze_e3


def bar(close, open_=None, high=None, low=None):
    open_ = close if open_ is None else open_
    high = max(close, open_) + 0.2 if high is None else high
    low = min(close, open_) - 0.2 if low is None else low
    return {"open": open_, "high": high, "low": low, "close": close}


def trend_series(start=100.0, step=0.2, count=100):
    return [bar(start + i * step) for i in range(count)]


def test_e3_v10_uses_the_current_causal_v8_contract():
    result = analyze_e3(trend_series())
    assert result["analysis_status"] == "COMPLETE"
    assert result["architecture"] == "E3_PROFESSIONAL_MARKET_STRUCTURE_CAUSAL_V8"
    assert result["reasoning_role"] == "MARKET_STRUCTURE_ANALYST"
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["decision"] is None
    assert result["gate"] is None


def test_e3_v10_never_uses_upstream_direction_decision_or_gate():
    result = analyze_e3(trend_series())
    trace = result["reasoning_trace"]
    assert trace["upstream_inputs_used"] is False
    assert result["upstream_direction_used"] is False
    assert result["upstream_decisions_used"] is False
    assert result["upstream_gates_used"] is False


def test_e3_v10_keeps_external_and_internal_structure_separate():
    result = analyze_e3(trend_series())
    external = result["external_structure"]
    internal = result["internal_structure"]
    assert isinstance(external, dict)
    assert isinstance(internal, dict)
    assert external["basis"] == "ORDERED_CONFIRMED_SWINGS"
    assert internal["basis"] == "ORDERED_CONFIRMED_SWINGS"
    assert external is not internal


def test_e3_v10_does_not_promote_raw_slope_or_counts_to_structural_authority():
    result = analyze_e3(trend_series())
    assert result["reasoning_trace"]["slope_is_structural_authority"] is False
    assert result["external_structure"]["counts_used_as_authority"] is False
    assert result["internal_structure"]["counts_used_as_authority"] is False


def test_e3_v10_requires_a_current_closed_candle_event_for_bos():
    bars = trend_series(count=100)
    result = analyze_e3(bars)
    assert result["bos"]["confirmed"] is False
    assert result["break_lifecycle"]["current"] is False


def test_e3_v10_wick_only_move_does_not_confirm_a_break():
    bars = [bar(100.0 + (i % 2) * 0.5) for i in range(100)]
    previous_close = bars[-1]["close"]
    bars[-1] = bar(previous_close, open_=previous_close, high=previous_close + 10.0, low=previous_close - 0.2)
    result = analyze_e3(bars)
    assert result["bos"]["confirmed"] is False


def test_e3_v10_mixed_structure_does_not_invent_protected_direction():
    bars = []
    values = [100, 102, 101, 103, 102, 101, 103, 102, 104, 103, 102, 104, 103, 101, 102, 100]
    for i, close in enumerate(values):
        open_ = values[i - 1] if i else close
        bars.append(bar(close, open_=open_))
    bars.extend(trend_series(start=100, step=0.05, count=60))
    result = analyze_e3(bars)
    protected = result["protected_structure"]
    assert protected["active_regime"] in {"UP", "DOWN", "MIXED", "NEUTRAL"}
    if protected["active_regime"] in {"MIXED", "NEUTRAL"}:
        assert protected["completeness"] == "NO_DIRECTIONAL_REGIME"


def test_e3_v10_structure_invalidation_does_not_equal_reversal_confirmation():
    result = analyze_e3(trend_series(start=120.0, step=-0.2, count=100))
    invalidation = result["structural_invalidation"]
    assert "confirmed" in invalidation
    assert "invalidates_current_external_thesis" in invalidation
    assert "does_not_confirm_reversal" in invalidation
    assert invalidation["does_not_confirm_reversal"] is True


def test_e3_v10_exposes_causal_structure_authority_without_trade_authority():
    result = analyze_e3(trend_series())
    detail = result["authority_detail"]
    assert detail["authority_basis"] in {"EXTERNAL_STRUCTURE", "INTERNAL_STRUCTURE", "NONE"}
    assert "decision_rule" in detail
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
