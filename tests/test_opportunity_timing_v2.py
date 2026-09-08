from production_v2.opportunity_timing import classify_opportunity_timing


def test_young_opportunity_is_too_late_when_price_left_execution_zone():
    result = classify_opportunity_timing({
        "direction": "SELL",
        "event": "HIGH_FAILED_BREAK_RECLAIM",
        "event_age_bars": 1,
        "event_level": 100.0,
        "price": 101.0,
        "event_atr_frozen": 1.0,
        "execution_zone": {"low": 99.8, "high": 100.2},
        "opportunity_strength": 90,
        "available_space_atr_short": 1.5,
    })
    assert result["phase"] == "LATE_OPPORTUNITY"
    assert result["chase_prohibited"] is True
    assert result["late_by_displacement"] is True


def test_older_opportunity_can_remain_active_inside_execution_zone():
    result = classify_opportunity_timing({
        "direction": "SELL",
        "event": "HIGH_FAILED_BREAK_RECLAIM",
        "event_age_bars": 4,
        "event_level": 100.0,
        "price": 100.1,
        "event_atr_frozen": 1.0,
        "execution_zone": {"low": 99.8, "high": 100.2},
        "opportunity_strength": 90,
        "available_space_atr_short": 1.5,
    })
    assert result["phase"] != "LATE_OPPORTUNITY"
    assert result["chase_prohibited"] is False
    assert result["displacement_atr"] == 0.1
