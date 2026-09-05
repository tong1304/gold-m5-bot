from production_v2.e4_event_lifecycle_surgery import _repair


def _bar(ts, close):
    return {"timestamp": ts, "open": close - 1.0, "high": close + 2.0, "low": close - 2.0, "close": close, "is_closed": True}


def _output(direction="UP"):
    return {
        "event": {"type": "HIGH_ACCEPTANCE_CANDIDATE", "directional_implication": direction, "event_level": 100.0, "event_atr": 10.0, "event_candle_id": "2026-09-05T16:30:00Z"},
        "event_id": f"2026-09-05T16:30:00Z|HIGH_ACCEPTANCE_CANDIDATE|HIGH|100|{direction}",
        "event_candle_id": "2026-09-05T16:30:00Z", "event_level": 100.0, "event_atr_frozen": 10.0,
        "auction_state": "PENDING", "auction_phase": "PENDING", "event_age_bars": 0,
    }


def test_event_age_uses_evaluation_timestamp_when_bars_lag_one_candle():
    bars = [_bar("2026-09-05T16:25:00Z", 98.0), _bar("2026-09-05T16:30:00Z", 103.0), _bar("2026-09-05T16:35:00Z", 104.0)]
    repaired = _repair(_output(), bars, "2026-09-05T16:40:00Z")
    assert repaired["auction_lifecycle_repaired"] is True
    assert repaired["event_age_bars"] == 2
    assert repaired["auction_state"] == "CONFIRMED"
    assert repaired["follow_through_bars"] == 2


def test_pending_event_does_not_age_from_last_bar_when_evaluation_is_same_candle():
    bars = [_bar("2026-09-05T16:25:00Z", 98.0), _bar("2026-09-05T16:30:00Z", 103.0)]
    repaired = _repair(_output(), bars, "2026-09-05T16:30:00Z")
    assert repaired["event_age_bars"] == 0
    assert repaired["auction_state"] == "PENDING"


def test_directionless_pending_event_still_gets_age_repair_without_inventing_direction():
    bars = [_bar("2026-09-05T22:25:00Z", 79820.0), _bar("2026-09-05T22:30:00Z", 79847.0)]
    output = _output("NEUTRAL")
    output["event"]["type"] = "HIGH_LIQUIDITY_INTERACTION"
    output["event_level"] = 79847.0
    output["event_atr_frozen"] = 10.0
    repaired = _repair(output, bars, "2026-09-05T22:35:00Z")
    assert repaired["event_age_bars"] == 1
    assert repaired["auction_state"] == "PENDING"
    assert repaired["auction_lifecycle_repair_reason"] == "AGE_ONLY_NO_DIRECTIONAL_PROOF"
