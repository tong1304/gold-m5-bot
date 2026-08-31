from production_v2.e6_brain import _direction, analyze_e6


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
    assert source == "E4_TERMINAL_AUCTION"


def test_invalidated_structure_blocks_setup_direction_in_e6():
    bars = []
    price = 100.0
    for i in range(80):
        bars.append({"open": price, "high": price + 1.0, "low": price - 1.0, "close": price + 0.1})
        price += 0.1

    class Result:
        def __init__(self, output):
            self.output = output

    upstream = {
        "E1": Result({"directional_pressure": "UP", "finding": "MARKET_STATE=TRANSITION"}),
        "E2": Result({"direction": "NEUTRAL", "finding": "UNRESOLVED"}),
        "E3": Result({
            "finding": "BULLISH_STRUCTURE_INVALIDATED",
            "internal_state": "MIXED",
            "external_state": "UP",
            "lifecycle": "INVALIDATED",
            "invalidation": "BULLISH_STRUCTURE_INVALIDATED",
        }),
        "E4": Result({
            "event": "LOW_SWEEP_REJECTION",
            "auction_state": "PENDING",
            "response_actor": "BUYERS",
            "event_level": 92.0,
            "event_id": "test-invalidated-structure",
        }),
        "E5": Result({
            "available_space_atr_long": 2.0,
            "available_space_atr_short": 2.0,
            "repricing_state": "REPRICING_STARTING",
            "value_response": "REJECTED_BELOW_VALUE",
        }),
    }

    result = analyze_e6({"bars": bars}, upstream)

    assert result.output["state"] in {"INVALIDATED", "NO_SETUP"}
    assert result.output["direction"] == "NEUTRAL"
    assert "E3_STRUCTURE_INVALIDATED" in result.output["reason_codes"]
