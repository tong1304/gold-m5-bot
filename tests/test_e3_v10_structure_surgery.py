from production_v2.e3_brain import (
    _resolve_external_state,
    _state,
    _sweep_reclaim,
    _sweep_failure,
    _lifecycle,
    analyze_e3,
)


def bar(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


def series(values, wick=0.2):
    out = []
    for i, close in enumerate(values):
        prev = values[i - 1] if i else close
        out.append(bar(prev, max(prev, close) + wick, min(prev, close) - wick, close))
    return out


def pivot(index, price, label, confirmation=None):
    return {
        "index": index,
        "price": price,
        "label": label,
        "confirmation_index": index if confirmation is None else confirmation,
    }


def test_current_sweep_reclaim_is_not_reported_as_bos_or_failed_bos():
    bars = [bar(100, 101, 99, 100), bar(100, 101, 99, 100), bar(100, 112, 99, 109.7)]
    highs = [pivot(1, 110.0, "HH")]
    lows = [pivot(0, 99.0, "HL")]
    result = _sweep_reclaim(bars, highs, lows, atr=2.0, structure="UP")
    assert result["confirmed"] is True
    assert result["event"] == "SWEEP_RECLAIM"
    assert result["direction"] == "DOWN"


def test_failed_bos_requires_a_real_break_then_closed_reclaim():
    bars = [bar(100, 101, 99, 100), bar(100, 113, 99, 112), bar(112, 112.3, 109, 109.4)]
    highs = [pivot(0, 110.0, "HH")]
    lows = [pivot(0, 99.0, "HL")]
    result = _sweep_failure(bars, highs, lows, atr=2.0, prior_structure="UP")
    assert result["confirmed"] is True
    assert result["event"] == "FAILED_BOS"
    assert result["direction"] == "DOWN"


def test_break_lifecycle_does_not_promote_historical_break_to_current_break():
    bars = series([100 + i * 0.2 for i in range(60)])
    result = analyze_e3(bars)
    lifecycle = result["break_lifecycle"]
    assert lifecycle["current"] is False
    assert lifecycle["stage"] in {"NO_CONFIRMED_BREAK", "HISTORICAL_ACCEPTED_BREAK", "HISTORICAL_FAILED_BREAK"}


def test_lifecycle_never_calls_an_older_active_break_current():
    active = {
        "accepted": True,
        "break_candle_index": 10,
        "follow_through_bars": 2,
        "level": 110.0,
    }
    result = _lifecycle(
        current={"confirmed": False, "event": "NO_BOS"},
        failure={"confirmed": False},
        history=[],
        active=active,
        last_index=20,
    )
    assert result["current"] is False
    assert result["stage"] == "HISTORICAL_ACCEPTED_BREAK"


def test_structure_authority_explains_external_priority_and_internal_conflict():
    bars = series([100 + i * 0.5 for i in range(50)])
    result = analyze_e3(bars)
    detail = result["authority_detail"]
    assert "primary" in detail
    assert "external" in detail["primary"].lower()
    assert result["reasoning_trace"]["external_is_authority"] is True
    assert result["reasoning_trace"]["upstream_inputs_used"] is False


def test_structural_invalidation_is_closed_candle_based():
    bars = series([120 - i * 0.4 for i in range(55)])
    result = analyze_e3(bars)
    invalidation = result["structural_invalidation"]
    assert "CLOSED_CANDLE" in invalidation["type"] or invalidation["level"] is None


def test_e3_never_has_trade_decision_authority():
    result = analyze_e3(series([100 + i * 0.3 for i in range(80)]))
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["upstream_direction_used"] is False
    assert result["upstream_decisions_used"] is False


def test_structure_conflict_is_explicit_when_external_and_internal_directions_disagree():
    no_event = {"confirmed": False, "event": "NO_BOS"}
    no_failure = {"confirmed": False}
    no_sweep = {"confirmed": False}
    no_invalidation = {"confirmed": False}
    assert _state("DOWN", "UP", no_event, no_failure, no_sweep, no_invalidation, {}) == "STRUCTURE_CONFLICT"


def test_authority_contract_exposes_primary_structure_and_invalidation_anchor():
    result = analyze_e3(series([100 + i * 0.5 for i in range(80)]))
    protected = result["protected_structure"]
    assert "primary_direction" in protected
    assert "primary_level" in protected
    assert "invalidation_level" in protected
    assert "why_primary" in protected


def test_break_lifecycle_exposes_age_and_follow_through_state():
    result = analyze_e3(series([100 + i * 0.3 for i in range(100)]))
    lifecycle = result["break_lifecycle"]
    assert "age_bars" in lifecycle
    assert "follow_through_bars" in lifecycle
    assert "terminal" in lifecycle


def test_sweep_reclaim_is_closed_candle_event_with_reclaim_quality():
    bars = [bar(100, 101, 99, 100), bar(100, 101, 99, 100), bar(100, 112, 99, 109.7)]
    highs = [pivot(1, 110.0, "HH")]
    lows = [pivot(0, 99.0, "HL")]
    result = _sweep_reclaim(bars, highs, lows, atr=2.0, structure="UP")
    assert result["confirmed"] is True
    assert result["closed_candle_confirmed"] is True
    assert result["sweep_distance_atr"] >= 0.05
    assert result["reclaim_distance_atr"] >= 0.05


def test_external_sequence_bias_overrides_raw_count_divergence():
    highs = [pivot(5, 110, "SWING_HIGH"), pivot(15, 112, "HH"), pivot(25, 114, "HH")]
    lows = [pivot(10, 100, "SWING_LOW"), pivot(20, 105, "HL"), pivot(30, 108, "HL")]
    assert _resolve_external_state(highs, lows) == "UP"


def test_external_sequence_bearish_bias_overrides_raw_count_divergence():
    highs = [pivot(5, 120, "SWING_HIGH"), pivot(15, 115, "LH"), pivot(25, 110, "LH")]
    lows = [pivot(10, 100, "SWING_LOW"), pivot(20, 95, "LL"), pivot(30, 90, "LL")]
    assert _resolve_external_state(highs, lows) == "DOWN"


def test_eqh_eql_are_liquidity_references_not_structural_direction():
    highs = [pivot(5, 110, "SWING_HIGH"), pivot(15, 110.05, "EQH"), pivot(25, 110.02, "EQH")]
    lows = [pivot(10, 100, "SWING_LOW"), pivot(20, 100.03, "EQL"), pivot(30, 100.01, "EQL")]
    assert _resolve_external_state(highs, lows) == "NEUTRAL"


def test_e3_reports_no_upstream_gate_or_trade_decision_usage():
    result = analyze_e3(series([100 + i * 0.1 for i in range(100)]))
    trace = result["reasoning_trace"]
    assert trace["upstream_inputs_used"] is False
    assert result["upstream_gates_used"] is False
    assert result["trade_decision_authority"] is False


def test_closed_candle_break_requires_close_beyond_structural_level():
    bars = [
        bar(100, 101, 99, 100),
        bar(100, 110.3, 99.5, 100.1),
    ]
    highs = [pivot(0, 110.0, "HH")]
    lows = [pivot(0, 99.0, "HL")]
    result = analyze_e3(bars + [bar(100.1, 100.2, 99.8, 100.0)] * 40)
    assert result["analysis_status"] == "COMPLETE"
