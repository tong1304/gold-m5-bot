from production_v2.e3_brain import _protected_structure, _sweep_reclaim, _semantic_structure_state, _break_event_lifecycle, analyze_e3


def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def pivot(index, price, label):
    return {"index": index, "price": price, "label": label, "confirmation_index": index}


def test_non_ideal_anchor_is_never_promoted_to_protected():
    highs = [pivot(5, 100, "SWING_HIGH"), pivot(15, 110, "SWING_HIGH")]
    lows = [pivot(10, 95, "SWING_LOW"), pivot(20, 90, "LL")]
    p = _protected_structure("DOWN", highs, lows)
    assert p["anchor_status"] == "MISSING"
    assert p["anchor_quality"] == "MISSING"
    assert p["anchor_is_ideal"] is False


def test_sweep_reclaim_detects_structural_swing_liquidity():
    bars = [bar(100, 101, 99, 100), bar(100, 101, 99, 100), bar(100, 113, 99, 109.8)]
    highs = [pivot(1, 110.0, "LH")]
    lows = [pivot(0, 99.0, "HL")]
    result = _sweep_reclaim(bars, highs, lows, atr=2.0, structure="DOWN")
    assert result["confirmed"] is True
    assert result["event"] == "SWEEP_RECLAIM"
    assert result["lifecycle"] == "RECLAIM"
    assert result["liquidity_type"] == "STRUCTURAL_SWING_HIGH"


def test_semantics_reject_stale_bullish_pair_after_new_opposite_leg():
    highs = [pivot(20, 100, "SWING_HIGH"), pivot(60, 95, "LH"), pivot(90, 105, "HH")]
    lows = [pivot(40, 90, "HL"), pivot(70, 85, "LL")]
    result = _semantic_structure_state(highs, lows)
    assert result["state"] == "MIXED"
    assert result["counts_used_as_authority"] is False
    assert result["structural_sequence"]


def test_semantics_accepts_ordered_bearish_structure():
    highs = [pivot(20, 100, "SWING_HIGH"), pivot(50, 95, "LH"), pivot(80, 90, "LH")]
    lows = [pivot(35, 90, "SWING_LOW"), pivot(65, 85, "LL"), pivot(95, 80, "LL")]
    result = _semantic_structure_state(highs, lows)
    assert result["state"] == "DOWN"


def test_semantics_accepts_ordered_bullish_structure():
    highs = [pivot(20, 100, "SWING_HIGH"), pivot(50, 105, "HH"), pivot(80, 110, "HH")]
    lows = [pivot(35, 90, "SWING_LOW"), pivot(65, 95, "HL"), pivot(95, 100, "HL")]
    result = _semantic_structure_state(highs, lows)
    assert result["state"] == "UP"


def test_break_lifecycle_exposes_normalized_professional_stages():
    failed = _break_event_lifecycle([
        {"event": "CONFIRMED_BOS", "direction": "UP", "level": 100, "break_candle_index": 10,
         "status": "FAILED_BREAK_RECLAIMED", "failure_candle_index": 13}
    ], 20)
    assert failed["stage"] == "HISTORICAL_FAILED_BREAK"
    assert failed["terminal"] is True
    assert failed["current"] is False

    accepted = _break_event_lifecycle([
        {"event": "CONFIRMED_BOS", "direction": "DOWN", "level": 100, "break_candle_index": 10,
         "status": "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH", "acceptance_candle_index": 12, "accepted": True}
    ], 20)
    assert accepted["stage"] == "HISTORICAL_ACCEPTED_BREAK"
    assert accepted["accepted"] is True


def test_e3_reasoning_trace_explains_current_vs_historical_structure():
    bars = []
    closes = [120 - i * 0.4 for i in range(100)]
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i else c
        bars.append(bar(prev, max(prev, c) + 0.2, min(prev, c) - 0.2, c))
    result = analyze_e3(bars)
    trace = result["reasoning_trace"]
    assert "current_state" in trace
    assert "historical_context" in trace
    assert "invalidation_rule" in trace
    assert "structure_narrative" in trace


def test_e3_does_not_treat_internal_structure_as_market_authority():
    closes = [100 + i * 0.2 for i in range(120)]
    bars = []
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i else c
        bars.append(bar(prev, max(prev, c) + 0.2, min(prev, c) - 0.2, c))
    result = analyze_e3(bars)
    assert result["reasoning_trace"]["internal_bos_has_market_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
