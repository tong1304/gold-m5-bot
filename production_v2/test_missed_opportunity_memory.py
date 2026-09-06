from production_v2.missed_opportunity import measure_terminal_opportunity


def test_terminal_measurement_records_missed_trade_without_authorizing():
    previous = {
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "state": "WAITING",
        "setup": "TREND_PULLBACK",
        "thesis_proven": True,
        "entry": 100.0,
        "stop_loss": 102.0,
        "origin_candle": "2026-09-06T10:00:00Z",
        "trade_authorized": False,
    }
    current = {
        "state": "EXPIRED",
        "opportunity_id": previous["opportunity_id"],
        "direction": "SELL",
        "bars_waited": 5,
        "invalidation_reason": "WATCH_MAX_AGE_REACHED",
        "last_evaluated_candle": "2026-09-06T10:25:00Z",
    }
    bars = [
        {"timestamp": "2026-09-06T10:05:00Z", "high": 100.5, "low": 99.0},
        {"timestamp": "2026-09-06T10:10:00Z", "high": 99.2, "low": 97.5},
    ]

    result = measure_terminal_opportunity(previous, current, bars)

    assert result["classification"] == "MISSED_GOOD_TRADE"
    assert result["opportunity_id"] == previous["opportunity_id"]
    assert result["trade_authorized"] is False
    assert result["terminal_state"] == "EXPIRED"


def test_terminal_measurement_is_good_wait_for_unproven_watch():
    previous = {
        "opportunity_id": "BUY|OPPORTUNITY_WATCH",
        "direction": "BUY",
        "state": "WATCHING",
        "setup": "OPPORTUNITY_WATCH",
        "thesis_proven": False,
        "origin_candle": "2026-09-06T10:00:00Z",
    }
    current = {
        "state": "INVALIDATED",
        "opportunity_id": previous["opportunity_id"],
        "direction": "BUY",
        "invalidation_reason": "UPSTREAM_CAUSAL_EVIDENCE_LOST",
        "last_evaluated_candle": "2026-09-06T10:10:00Z",
    }

    result = measure_terminal_opportunity(previous, current, [])

    assert result["classification"] == "GOOD_WAIT"
    assert result["measured"] is True
    assert result["trade_authorized"] is False


def test_terminal_measurement_does_not_use_counter_direction_geometry():
    previous = {
        "opportunity_id": "BUY|OPPORTUNITY_WATCH",
        "direction": "BUY",
        "state": "WAITING",
        "setup": "BREAKOUT",
        "thesis_proven": True,
        "entry": 100.0,
        "stop_loss": 98.0,
        "origin_candle": "2026-09-06T10:00:00Z",
    }
    current = {
        "state": "REPLACED",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "previous_opportunity_id": previous["opportunity_id"],
        "last_evaluated_candle": "2026-09-06T10:10:00Z",
    }
    bars = [{"timestamp": "2026-09-06T10:05:00Z", "high": 103.0, "low": 99.5}]

    result = measure_terminal_opportunity(previous, current, bars)

    assert result["opportunity_id"] == previous["opportunity_id"]
    assert result["direction"] == "BUY"
    assert result["terminal_state"] == "REPLACED"
