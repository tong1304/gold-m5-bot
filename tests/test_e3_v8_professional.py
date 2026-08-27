from production_v2.e3_brain_v8 import _break, _external_event, _sequence_quality, DOWN, UP, NEUTRAL


def test_wick_only_break_is_not_confirmed():
    bar = {"open": 99.0, "high": 101.5, "low": 98.8, "close": 99.4}
    result = _break(bar, 100.0, UP, 1.0)
    assert result["confirmed"] is False
    assert result["wick_only"] is True


def test_close_with_displacement_confirms_bos():
    bar = {"open": 100.0, "high": 101.5, "low": 99.8, "close": 101.0}
    result = _break(bar, 100.5, UP, 1.0)
    assert result["confirmed"] is True
    assert result["direction"] == UP


def test_external_down_uses_ll_for_bos_and_lh_for_choch():
    highs = [{"index": 10, "price": 105.0, "label": "LH"}]
    lows = [{"index": 8, "price": 98.0, "label": "LL"}]

    continuation_bar = {"open": 98.2, "high": 98.4, "low": 96.5, "close": 97.0}
    bos = _external_event(continuation_bar, DOWN, highs, lows, 1.0, 20)
    assert bos["event"] == "CONFIRMED_BOS"
    assert bos["direction"] == DOWN
    assert bos["swing_label"] == "LL"

    invalidation_bar = {"open": 104.0, "high": 106.5, "low": 103.8, "close": 106.0}
    choch = _external_event(invalidation_bar, DOWN, highs, lows, 1.0, 21)
    assert choch["event"] == "CONFIRMED_CHOCH"
    assert choch["direction"] == UP
    assert choch["swing_label"] == "LH"


def test_same_candle_external_break_conflict_has_no_direction():
    highs = [{"index": 10, "price": 100.0, "label": "LH"}]
    lows = [{"index": 8, "price": 98.0, "label": "LL"}]
    bar = {"open": 99.0, "high": 101.0, "low": 97.0, "close": 99.5}
    result = _external_event(bar, DOWN, highs, lows, 1.0, 20)
    assert result["event"] == "STRUCTURE_CONFLICT"
    assert result["confirmed"] is False
    assert result["direction"] == NEUTRAL


def test_sequence_quality_requires_alternating_structure():
    highs = [
        {"index": 1, "price": 101, "label": "SWING_HIGH"},
        {"index": 3, "price": 102, "label": "HH"},
    ]
    lows = [
        {"index": 2, "price": 99, "label": "SWING_LOW"},
        {"index": 4, "price": 100, "label": "HL"},
    ]
    quality, state = _sequence_quality(highs, lows)
    assert quality >= 0.5
    assert state == "SEQUENCE_VALID"
