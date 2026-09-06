from production_v2.e4_event_lifecycle_surgery import _repair


def _bar(ts: str, close: float) -> dict:
    return {"timestamp": ts, "open": close, "high": close, "low": close, "close": close}


def test_repaired_event_age_is_consistent_in_nested_evidence_audit_views():
    bars = [
        _bar("2026-09-06T06:00:00Z", 79952.90),
        _bar("2026-09-06T06:05:00Z", 79957.87),
        _bar("2026-09-06T06:10:00Z", 79960.00),
    ]
    output = {
        "event_candle_id": "2026-09-06T06:00:00Z",
        "event_level": 79952.90,
        "event_atr": 57.586429,
        "auction_state": "REJECTION_PENDING",
        "event_age_bars": 0,
        "evidence_audit": {
            "interpretation": {"event_age_bars": 0},
            "decision": {"event_age_bars": 0},
        },
        "event": {
            "event_candle_id": "2026-09-06T06:00:00Z",
            "event_level": 79952.90,
            "event_atr": 57.586429,
            "directional_implication": "DOWN",
        },
    }
    repaired = _repair(output, bars, "2026-09-06T06:10:00Z")
    assert repaired["event_age_bars"] == 2
    assert repaired["evidence_audit"]["interpretation"]["event_age_bars"] == 2
    assert repaired["evidence_audit"]["decision"]["event_age_bars"] == 2
