from production_v2.opportunity_timing import classify_opportunity_timing


def test_early_high_quality_event_uses_fast_evidence_cycle():
    result = classify_opportunity_timing({
        "direction": "SELL",
        "event": "HIGH_FAILED_BREAK_RECLAIM",
        "event_age_bars": 0,
        "confidence": 0.80,
        "available_space_atr": 1.0,
        "auction_state": "PENDING",
    })
    assert result["phase"] == "EARLY_OPPORTUNITY"
    assert result["decision_speed"] == "FAST"
    assert result["fast_path_eligible"] is True
    assert result["chase_prohibited"] is False


def test_confirmed_opportunity_uses_standard_speed_when_fresh():
    result = classify_opportunity_timing({
        "direction": "BUY",
        "event": "LOW_SWEEP_REJECTION",
        "event_age_bars": 1,
        "confidence": 0.82,
        "available_space_atr": 1.2,
        "confirmation_state": "CONFIRMED",
    })
    assert result["phase"] == "CONFIRMED_OPPORTUNITY"
    assert result["decision_speed"] == "STANDARD"
    assert result["confirmed"] is True


def test_late_opportunity_slows_and_blocks_chasing():
    result = classify_opportunity_timing({
        "direction": "SELL",
        "event": "HIGH_FAILED_BREAK_RECLAIM",
        "event_age_bars": 2,
        "confidence": 0.90,
        "available_space_atr": 1.0,
        "confirmation_state": "CONFIRMED",
    })
    assert result["phase"] == "LATE_OPPORTUNITY"
    assert result["decision_speed"] == "SLOW"
    assert result["chase_prohibited"] is True
    assert result["fast_path_eligible"] is False


def test_large_event_displacement_is_late_even_on_first_recheck():
    result = classify_opportunity_timing({
        "direction": "SELL",
        "event": "HIGH_FAILED_BREAK_RECLAIM",
        "event_age_bars": 1,
        "confidence": 0.88,
        "available_space_atr": 1.0,
        "event_level": 4425.73,
        "price": 4422.27,
        "event_atr_frozen": 4.920714,
    })
    assert result["phase"] == "LATE_OPPORTUNITY"
    assert result["late_by_displacement"] is True
    assert result["decision_speed"] == "SLOW"
