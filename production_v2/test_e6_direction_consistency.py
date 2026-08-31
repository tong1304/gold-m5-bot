from production_v2.e6_brain import _direction


def test_pending_auction_cannot_override_agreeing_context():
    e1 = {"directional_pressure": "UP", "finding": "MARKET_STATE=RANGE"}
    e2 = {"direction": "NEUTRAL", "finding": "UNRESOLVED"}
    e3 = {
        "finding": "BULLISH_STRUCTURE",
        "internal_state": "UP",
        "external_state": "UP",
    }
    e4 = {
        "event": "HIGH_FAILED_BREAK_RECLAIM",
        "auction_state": "PENDING",
        "response_actor": "SELLERS",
        "event_level": 4462.42,
        "event_id": "test-event",
    }

    direction, support, conflicts, source = _direction(e1, e2, e3, e4)

    assert direction == "BUY"
    assert source in {"E1_E3_DIRECTIONAL_CORE", "E3_STRUCTURE_CONVERGENCE"}
    assert "DIRECTIONAL_EVIDENCE_CONFLICT" in conflicts


def test_confirmed_auction_can_supply_direction_when_context_has_no_direction():
    e1 = {"directional_pressure": "NEUTRAL", "finding": "MARKET_STATE=RANGE"}
    e2 = {"direction": "NEUTRAL", "finding": "UNRESOLVED"}
    e3 = {
        "finding": "MIXED_STRUCTURE",
        "internal_state": "NEUTRAL",
        "external_state": "NEUTRAL",
    }
    e4 = {
        "event": "LOW_ACCEPTANCE_CANDIDATE",
        "auction_state": "CONFIRMED",
        "response_actor": "SELLERS",
        "event_level": 78000.0,
        "event_id": "test-event-confirmed",
    }

    direction, support, conflicts, source = _direction(e1, e2, e3, e4)

    assert direction == "SELL"
    assert source == "E4_EVENT_WITH_CONTEXT_CONFLICT"
