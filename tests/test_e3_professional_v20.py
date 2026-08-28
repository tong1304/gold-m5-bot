from production_v2.e3_brain import (
    _semantic_structure_state,
    _protected_structure,
    _break_event_lifecycle,
    _structure_authority,
)


def pivot(index, price, label):
    return {"index": index, "price": float(price), "label": label, "confirmation_index": index}


def test_semantic_state_uses_ordered_swing_sequence_not_label_counts():
    highs = [
        pivot(10, 110, "SWING_HIGH"),
        pivot(20, 108, "LH"),
        pivot(30, 112, "HH"),
    ]
    lows = [
        pivot(15, 100, "SWING_LOW"),
        pivot(25, 103, "HL"),
        pivot(35, 101, "LL"),
    ]
    result = _semantic_structure_state(highs, lows)
    assert result["state"] == "MIXED"
    assert result["basis"] == "ORDERED_SWING_SEQUENCE"
    assert result["counts_used_as_authority"] is False


def test_protected_anchor_requires_confirmed_structural_relation():
    highs = [
        pivot(10, 110, "SWING_HIGH"),
        pivot(20, 108, "LH"),
    ]
    lows = [
        pivot(15, 100, "SWING_LOW"),
        pivot(25, 95, "LL"),
    ]
    result = _protected_structure("DOWN", highs, lows)
    assert result["anchor_is_ideal"] is True
    assert result["anchor_status"] == "ACTIVE"
    assert result["protected_high"]["label"] == "LH"
    assert result["protected_low"]["label"] == "LL"


def test_break_lifecycle_separates_confirmation_acceptance_failure_and_currentness():
    history = [
        {
            "event": "CONFIRMED_BOS",
            "direction": "DOWN",
            "level": 100.0,
            "break_candle_index": 10,
            "acceptance_candle_index": 12,
            "failure_candle_index": None,
        }
    ]
    result = _break_event_lifecycle(history, last_index=20)
    assert result["stage"] == "HISTORICAL_ACCEPTED_BREAK"
    assert result["current"] is False
    assert result["accepted"] is True
    assert result["terminal"] is True


def test_structure_authority_explicitly_prioritizes_external_over_internal():
    result = _structure_authority(
        external={"state": "UP", "confidence": 0.8},
        internal={"state": "DOWN", "confidence": 0.95},
        protected={"anchor_status": "ACTIVE", "anchor_is_ideal": True},
        current_event={"confirmed": False},
        invalidation={"confirmed": False},
    )
    assert result["authority"] == "EXTERNAL"
    assert result["direction"] == "UP"
    assert result["internal_role"] == "CONTEXT_ONLY"
    assert result["count_role"] == "DESCRIPTIVE_ONLY"
