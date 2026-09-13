from production_v2.opportunity_repricing_continuation import apply_opportunity_repricing


def test_live_pending_opportunity_becomes_reprice_wait_instead_of_dead_no_trade():
    lifecycle = {
        "state": "WATCHING",
        "lifecycle_state": "WATCH",
        "opportunity_phase": "OPPORTUNITY_WATCH",
        "opportunity_id": "BUY|OPPORTUNITY_WATCH|evt-1",
        "direction": "BUY",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 1,
        "trade_authorized": False,
    }
    e4 = {"auction_state": "PENDING", "event_id": "evt-1"}
    e5 = {"available_space_atr_long": 0.89, "available_space_atr_short": 0.32}
    e8 = {
        "finding": "UNRESOLVED",
        "economic_stage": "EARLY_OPPORTUNITY_SCREEN",
        "trade_authorized": False,
        "reason_codes": ["REAL_RR_BELOW_MINIMUM", "NO_USABLE_STRUCTURAL_TARGET"],
    }

    result = apply_opportunity_repricing(lifecycle, e4=e4, e5=e5, e8=e8)

    assert result["state"] == "REPRICE_WAIT"
    assert result["opportunity_phase"] == "REPRICE_WAIT"
    assert result["wait_for"] == "NEXT_CLOSED_M5_CANDLE_REPRICE"
    assert result["trade_authorized"] is False
    assert result["economic_blockers_deferred"] is True
    assert result["opportunity_id"] == lifecycle["opportunity_id"]
