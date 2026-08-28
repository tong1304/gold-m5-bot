from production_v2.e3_brain import (
    DOWN,
    UP,
    _authority,
    _current_break,
    _invalidation,
    _protected_structure,
    _semantic_structure_state,
)


def _pivot(index, price, label, confirmation_index=None):
    return {"index": index, "price": float(price), "label": label, "confirmation_index": index + 2 if confirmation_index is None else confirmation_index}


def test_semantic_sequence_is_explicit_and_not_count_authority():
    highs = [_pivot(10, 100, "SWING_HIGH"), _pivot(20, 110, "HH"), _pivot(30, 108, "LH")]
    lows = [_pivot(15, 95, "SWING_LOW"), _pivot(25, 102, "HL"), _pivot(35, 98, "LL")]
    result = _semantic_structure_state(highs, lows)
    assert result["semantic_labels"] == ["HH", "HL", "LH", "LL"]
    assert result["counts_used_as_authority"] is False
    assert result["semantic_sequence"]


def test_protected_structure_has_explicit_directional_anchor():
    highs = [_pivot(10, 100, "SWING_HIGH"), _pivot(20, 110, "HH")]
    lows = [_pivot(15, 95, "SWING_LOW"), _pivot(18, 102, "HL")]
    result = _protected_structure(UP, highs, lows)
    assert result["anchor_status"] == "ACTIVE"
    assert result["primary_label"] == "HL"
    assert result["invalidation_level"] == 102.0
    assert result["invalidation_type"] == "CLOSED_CANDLE_ACCEPTANCE_BELOW_PROTECTED_LOW"


def test_closed_candle_counter_break_is_explicit_choch():
    highs = [_pivot(0, 100, "SWING_HIGH", 0), _pivot(0, 110, "HH", 0)]
    lows = [_pivot(0, 95, "SWING_LOW", 0), _pivot(0, 102, "HL", 0)]
    bars = [
        {"open": 104, "high": 105, "low": 103, "close": 104},
        {"open": 103, "high": 104, "low": 100, "close": 100},
    ]
    result = _current_break(bars, highs, lows, atr=2.0, structure=UP, scope="EXTERNAL")
    assert result["event"] == "CONFIRMED_CHOCH", result
    assert result["direction"] == DOWN
    assert result["closed_candle_confirmed"] is True
    assert result["scope"] == "EXTERNAL"


def test_authority_is_explicit_and_internal_never_promotes_itself():
    protected = _protected_structure(DOWN, [_pivot(20, 110, "LH")], [_pivot(10, 100, "SWING_LOW"), _pivot(25, 90, "LL")])
    result = _authority(DOWN, UP, "DOWN", "UP", {"confirmed": False}, {}, protected, {}, {"confirmed": False})
    assert result["authority"] == "EXTERNAL"
    assert result["direction"] == DOWN
    assert result["internal_role"] == "CONTEXT_ONLY"
    assert result["actionable"] is True


def test_invalidation_has_strict_semantic_status_and_does_not_claim_reversal():
    bars = [
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 98, "high": 99, "low": 94, "close": 95},
    ]
    protected = _protected_structure(UP, [_pivot(10, 110, "HH")], [_pivot(8, 102, "HL")])
    result = _invalidation(bars, UP, protected)
    assert result["status"] == "INVALIDATED"
    assert result["confirmed"] is True
    assert result["does_not_confirm_reversal"] is True


def test_e3_liquidity_contract_is_observation_only_and_requires_e4():
    from production_v2.e3_brain import analyze_e3
    bars = []
    price = 100.0
    for i in range(100):
        close = price + (0.2 if i % 2 == 0 else -0.1)
        bars.append({"open": price, "high": max(price, close) + 0.2, "low": min(price, close) - 0.2, "close": close})
        price = close
    result = analyze_e3(bars)
    liquidity = result["current_liquidity"]
    assert liquidity["specialist_confirmation"] is False
    assert liquidity["confirmation_authority"] == "E4"
    assert liquidity["e4_confirmation_required"] is True
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
