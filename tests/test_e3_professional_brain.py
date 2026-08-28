from production_v2.e3_brain import (
    _current_break,
    _invalidation,
    _protected_structure,
    _resolve_external_state,
    _sweep_reclaim,
    _break_history,
    analyze_e3,
)


def bar(c, o=None, h=None, l=None):
    o = c if o is None else o
    h = max(c, o) + 0.2 if h is None else h
    l = min(c, o) - 0.2 if l is None else l
    return {"open": o, "high": h, "low": l, "close": c}


def test_external_state_prefers_coherent_hh_hl_sequence():
    highs = [{"label": "HH", "price": 105}, {"label": "HH", "price": 110}]
    lows = [{"label": "HL", "price": 95}, {"label": "HL", "price": 100}]
    assert _resolve_external_state(highs, lows) == "UP"


def test_external_state_prefers_coherent_lh_ll_sequence():
    highs = [{"label": "LH", "price": 105}, {"label": "LH", "price": 100}]
    lows = [{"label": "LL", "price": 95}, {"label": "LL", "price": 90}]
    assert _resolve_external_state(highs, lows) == "DOWN"


def test_protected_structure_is_defended_anchor():
    highs = [{"label": "HH", "price": 110, "index": 10}, {"label": "HH", "price": 115, "index": 20}]
    lows = [{"label": "HL", "price": 100, "index": 15}, {"label": "HL", "price": 105, "index": 25}]
    protected = _protected_structure("UP", highs, lows)
    assert protected["primary_level"] == 105
    assert protected["primary_label"] == "HL"
    assert protected["invalidation_level"] == 105


def test_bos_against_bearish_external_structure_is_choch():
    bars = [bar(100) for _ in range(10)]
    bars[-2] = bar(100, 99, 101, 98.8)
    bars[-1] = bar(102, 100, 102.5, 99.8)
    highs = [{"index": 8, "price": 100.0, "label": "LH", "confirmation_index": 8}]
    event = _current_break(bars, highs, [], 1.0, "DOWN")
    assert event["event"] == "CONFIRMED_CHOCH"
    assert event["closed_candle_confirmed"] is True


def test_failed_bos_is_reclaim_not_permanent_break():
    bars = [bar(100) for _ in range(12)]
    bars[9] = bar(100, 99, 100.2, 99.5)
    bars[10] = bar(101, 100, 101.5, 99.8)
    bars[11] = bar(99.8, 101, 101.2, 99.5)
    highs = [{"index": 9, "price": 100.0, "label": "LH", "confirmation_index": 9}]
    history, _ = _break_history(bars, highs, [], 1.0, "DOWN")
    assert any(x.get("status") == "FAILED_BREAK_RECLAIMED" for x in history)


def test_sweep_high_reclaim_is_bearish_liquidity_event():
    bars = [bar(100) for _ in range(10)]
    bars[-1] = bar(99.8, 100.2, 101.0, 99.0)
    highs = [{"index": 7, "price": 100.0, "label": "LH", "confirmation_index": 7}]
    event = _sweep_reclaim(bars, highs, [], 1.0, "DOWN")
    assert event["confirmed"] is True
    assert event["direction"] == "DOWN"


def test_sweep_low_reclaim_is_bullish_liquidity_event():
    bars = [bar(100) for _ in range(10)]
    bars[-1] = bar(100.2, 99.8, 100.5, 98.8)
    lows = [{"index": 7, "price": 99.0, "label": "HL", "confirmation_index": 7}]
    event = _sweep_reclaim(bars, [], lows, 1.0, "UP")
    assert event["confirmed"] is True
    assert event["direction"] == "UP"


def test_structural_invalidation_requires_closed_candle_acceptance():
    bars = [bar(99, 98.5, 99.2, 98.4) for _ in range(20)]
    protected = {
        "invalidation_level": 100,
        "invalidation_type": "CLOSED_CANDLE_ACCEPTANCE_BELOW_PROTECTED_LOW",
        "primary_label": "HL",
        "protected_low": {"label": "HL", "index": 10},
    }
    event = _invalidation(bars, "UP", protected)
    assert event["confirmed"] is True
    assert event["closed_candle_confirmed"] is True


def test_e3_never_uses_upstream_trade_authority():
    bars = [bar(100 + i * 0.2) for i in range(50)]
    output = analyze_e3(bars)
    assert output["upstream_inputs_used"] is False
    assert output["upstream_decisions_used"] is False
    assert output["upstream_gates_used"] is False
    assert output["trade_decision_authority"] is False
    assert output["decision_authority"] == "E9_ONLY"
