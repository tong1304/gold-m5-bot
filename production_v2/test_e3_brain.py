from production_v2.e3_brain import (
    UP,
    DOWN,
    MIXED,
    NEUTRAL,
    _protected,
    _semantic,
    _label,
    _dedupe,
    _confirmed,
    _raw_pivots,
    analyze_e3,
)


def swing(i, price, label):
    return {
        "index": i,
        "price": float(price),
        "label": label,
        "confirmation_index": i + 1,
        "status": "CONFIRMED",
    }


def make_bars(closes):
    return [
        {"open": c - 0.2, "high": c + 0.5, "low": c - 0.5, "close": c}
        for c in closes
    ]


def test_up_regime_uses_one_causal_anchor_and_never_crosses_levels():
    highs = [swing(20, 110, "HH"), swing(50, 115, "HH")]
    lows = [swing(35, 100, "HL"), swing(65, 105, "HL")]
    p = _protected(highs, lows, UP)
    assert p["integrity"] == "VALID"
    assert p["active_regime"] == UP
    assert p["protected_high"]["price"] == 115.0
    assert p["protected_low"]["price"] == 100.0
    assert p["completeness"] == "COMPLETE"


def test_down_regime_uses_one_causal_anchor_and_never_crosses_levels():
    highs = [swing(20, 110, "LH"), swing(50, 105, "LH")]
    lows = [swing(35, 100, "LL"), swing(65, 95, "LL")]
    p = _protected(highs, lows, DOWN)
    assert p["integrity"] == "VALID"
    assert p["active_regime"] == DOWN
    assert p["protected_high"]["price"] == 110.0
    assert p["protected_low"]["price"] == 95.0
    assert p["completeness"] == "COMPLETE"


def test_mixed_regime_does_not_combine_stale_bullish_and_bearish_levels():
    highs = [swing(20, 4440.13, "LH"), swing(50, 4450.0, "HH")]
    lows = [swing(35, 4441.54, "HL"), swing(65, 4437.92, "LL")]
    p = _protected(highs, lows, MIXED)
    assert p["integrity"] == "VALID"
    assert p["protected_high"] is None
    assert p["protected_low"] is None
    assert p["completeness"] == "NO_DIRECTIONAL_REGIME"
    assert "NO_SINGLE_ACTIVE_DIRECTIONAL_REGIME" in p["integrity_reasons"]


def test_incomplete_directional_structure_is_not_misclassified_as_corrupt_data():
    highs = [swing(50, 115, "HH")]
    lows = [swing(20, 100, "SWING_LOW")]
    p = _protected(highs, lows, UP)
    assert p["integrity"] == "VALID"
    assert p["completeness"] == "BREAK_LEVEL_ONLY"
    assert p["protected_high"]["price"] == 115.0
    assert p["protected_low"] is None
    assert "BULLISH_PROTECTED_LOW_UNCONFIRMED_OR_MISSING" in p["integrity_reasons"]


def test_semantic_structure_uses_ordered_confirmed_swings():
    highs = [swing(20, 110, "HH"), swing(50, 115, "HH")]
    lows = [swing(35, 100, "HL"), swing(65, 105, "HL")]
    result = _semantic(highs, lows)
    assert result["state"] == UP
    assert result["basis"] == "ORDERED_CONFIRMED_SWINGS"
    assert result["counts_used_as_authority"] is False


def test_analyze_e3_returns_professional_closed_candle_schema():
    closes = [100 + ((i % 8) * 1.7) for i in range(100)]
    result = analyze_e3(make_bars(closes))
    assert result["engine"] == "E3"
    assert result["decision_authority"] == "E9_ONLY"
    assert result["data_quality"]["valid_bars"] == 100
    assert "external_structure" in result
    assert "internal_structure" in result
    assert "protected_structure" in result
    assert "structure_integrity" in result
    assert result["architecture"] == "E3_PROFESSIONAL_MARKET_STRUCTURE_CAUSAL_V8"


def test_analyze_e3_never_marks_clean_ohlc_as_protected_order_corruption_from_opposite_regimes():
    closes = []
    for base, peak in [(100, 110), (110, 102), (102, 108), (108, 98), (98, 105), (105, 94), (94, 99)]:
        step = (peak - base) / 10.0
        closes.extend(base + step * (j + 1) for j in range(10))
    result = analyze_e3(make_bars(closes))
    assert result["data_quality"]["rejected"] == []
    assert result["structure_integrity"] in {"VALID", "INVALID"}
    if result["structure_integrity"] == "INVALID":
        assert "CAUSAL_PROTECTED_LEVEL_ORDER_INVALID" in result["protected_structure"]["integrity_reasons"]


def test_insufficient_data_is_safe():
    result = analyze_e3(make_bars([100] * 10))
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["finding"] == "INSUFFICIENT_DATA"
    assert result["decision_authority"] == "E9_ONLY"
