from production_v2.e3_brain import _authority, _current_break, _protected_structure, _state, UP, DOWN, MIXED


def swing(index, price, label, confirmation_index=None):
    return {"index": index, "price": price, "label": label, "confirmation_index": index if confirmation_index is None else confirmation_index}


def bar(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


def test_count_state_cannot_add_authority():
    protected = _protected_structure(UP, [swing(10, 105, "HH")], [swing(8, 99, "HL")])
    base = _authority(UP, MIXED, DOWN, UP, {"confirmed": False}, {"confirmed": False}, protected, {"confirmed": False}, {"confirmed": False}, UP, 0.8)
    aligned = _authority(UP, MIXED, UP, UP, {"confirmed": False}, {"confirmed": False}, protected, {"confirmed": False}, {"confirmed": False}, UP, 0.8)
    assert aligned["score"] == base["score"]
    assert "COUNT_STATE_DESCRIPTIVE_ONLY" not in [x for x in aligned["support"] if x]


def test_external_protected_anchor_is_authority_over_internal_structure():
    protected = _protected_structure(UP, [swing(10, 105, "HH")], [swing(8, 99, "HL")])
    assert protected["primary_direction"] == UP
    assert protected["primary_label"] == "HL"
    assert protected["invalidation_level"] == 99


def test_internal_break_cannot_become_external_bos_without_external_break():
    bars = [bar(100, 101, 99, 100), bar(100, 101.2, 99.5, 100.8), bar(100.8, 102.0, 100.2, 101.5)]
    highs = [swing(1, 101.0, "HH")]
    lows = [swing(0, 99.0, "HL")]
    event = _current_break(bars, highs, lows, 1.0, UP, "EXTERNAL")
    assert event["confirmed"] is True
    assert event["event"] == "CONFIRMED_BOS"


def test_closed_candle_is_required_for_structural_break():
    bars = [bar(100, 101, 99, 100), bar(100, 101.2, 99.5, 100.5), bar(100.5, 102.0, 100.0, 100.7)]
    highs = [swing(1, 101.0, "HH")]
    lows = [swing(0, 99.0, "HL")]
    event = _current_break(bars, highs, lows, 1.0, UP, "EXTERNAL")
    assert event["confirmed"] is False


def test_state_separates_event_from_continuation_state():
    state = _state(UP, UP, {"confirmed": False}, {"confirmed": False}, {"confirmed": False}, {"confirmed": False}, {"stage": "CURRENT_BREAK_ACCEPTED"})
    assert state == "BREAK_ACCEPTED"
