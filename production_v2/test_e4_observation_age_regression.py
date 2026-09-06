from production_v2.e4_event_lifecycle_surgery import _repair


def _bar(ts: str, close: float) -> dict:
    return {"timestamp": ts, "open": close, "high": close, "low": close, "close": close}


def test_repaired_event_age_rewrites_stale_observation_view():
    bars = [
        _bar("2026-09-06T07:00:00Z", 79785.43),
        _bar("2026-09-06T07:05:00Z", 79784.17),
    ]
    output = {
        "event_candle_id": "2026-09-06T07:00:00Z",
        "event_level": 79785.43,
        "event_atr": 45.525714,
        "auction_state": "PENDING",
        "event_age_bars": 0,
        "observations": [
            "event_candle_id=2026-09-06T07:00:00Z",
            "event_age_bars=0",
        ],
        "event": {
            "event_candle_id": "2026-09-06T07:00:00Z",
            "event_level": 79785.43,
            "event_atr": 45.525714,
            "directional_implication": "DOWN",
        },
    }

    repaired = _repair(output, bars, "2026-09-06T07:05:00Z")

    assert repaired["event_age_bars"] == 1
    assert "event_age_bars=1" in repaired["observations"]
    assert "event_age_bars=0" not in repaired["observations"]
