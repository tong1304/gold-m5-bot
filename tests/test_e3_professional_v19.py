from production_v2.e3_brain import _protected_structure, _sweep_reclaim, analyze_e3


def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def pivot(index, price, label):
    return {"index": index, "price": price, "label": label, "confirmation_index": index}


def test_non_ideal_anchor_is_provisional_not_protected():
    highs = [pivot(5, 100, "SWING_HIGH"), pivot(15, 110, "SWING_HIGH")]
    lows = [pivot(10, 95, "SWING_LOW"), pivot(20, 90, "LL")]
    p = _protected_structure("DOWN", highs, lows)
    assert p["anchor_status"] in {"MISSING", "PROVISIONAL"}
    assert p["anchor_quality"] in {"MISSING", "PROVISIONAL"}
    assert p["anchor_is_ideal"] is False


def test_sweep_reclaim_detects_structural_swing_liquidity():
    bars = [bar(100, 101, 99, 100), bar(100, 101, 99, 100), bar(100, 113, 99, 109.8)]
    highs = [pivot(1, 110.0, "LH")]
    lows = [pivot(0, 99.0, "HL")]
    result = __import__("production_v2.e3_brain", fromlist=["_sweep_reclaim"])._sweep_reclaim(
        bars, highs, lows, atr=2.0, structure="DOWN"
    )
    assert result["confirmed"] is True
    assert result["event"] == "SWEEP_RECLAIM"
    assert result["liquidity_type"] == "STRUCTURAL_SWING_HIGH"


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


def test_e3_never_calls_a_non_accepted_break_current():
    closes = [100 + i * 0.3 for i in range(100)]
    bars = []
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i else c
        bars.append(bar(prev, max(prev, c) + 0.2, min(prev, c) - 0.2, c))
    result = analyze_e3(bars)
    life = result["break_lifecycle"]
    if life["current"]:
        assert life["stage"] == "CURRENT_BREAK_AWAITING_FOLLOW_THROUGH"
        assert life["accepted"] is False
