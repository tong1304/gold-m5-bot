from production_v2 import opportunity_lifecycle_timing
from production_v2.opportunity_lifecycle_progression import advance_lifecycle_stage


def _install_test_wrapper():
    class Pipeline:
        pass
    pipeline = Pipeline()
    def original(previous, current_by_direction, *, leader="NEUTRAL", competition="UNCONTESTED"):
        return {"opportunities": {"BUY": {**current_by_direction["BUY"], "state": "WATCHING"}, "SELL": {**current_by_direction["SELL"], "state": "WATCHING"}}, "leader": leader, "competition": competition, "trade_authorized": False}
    pipeline.advance_opportunity_directions = original
    opportunity_lifecycle_timing.install(pipeline)
    return pipeline


def test_fast_early_opportunity_is_carried_to_lifecycle_and_next_candle():
    pipeline = _install_test_wrapper()
    result = pipeline.advance_opportunity_directions({}, {"BUY": {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "opportunity_phase": "EARLY_OPPORTUNITY", "opportunity_speed": "FAST"}}, leader="BUY")
    buy = result["opportunities"]["BUY"]
    assert buy["opportunity_phase"] == "EARLY_OPPORTUNITY"
    assert buy["opportunity_speed"] == "FAST"
    assert buy["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"
    assert buy["wait_for"] == "FAST_CLOSED_CANDLE_CONFIRMATION"
    assert buy["chase_prohibited"] is False
    assert result["opportunity_speed"] == "FAST"
    assert result["trade_authorized"] is False


def test_standard_early_opportunity_keeps_normal_confirmation_window():
    pipeline = _install_test_wrapper()
    result = pipeline.advance_opportunity_directions({}, {"SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "opportunity_phase": "EARLY_OPPORTUNITY", "opportunity_speed": "STANDARD"}}, leader="SELL")
    sell = result["opportunities"]["SELL"]
    assert sell["opportunity_speed"] == "STANDARD"
    assert sell["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"
    assert sell["wait_for"] == "CLOSED_CANDLE_CONFIRMATION"
    assert sell["chase_prohibited"] is False
    assert result["trade_authorized"] is False


def test_late_opportunity_is_chase_prohibited_and_waits_for_new_event():
    pipeline = _install_test_wrapper()
    result = pipeline.advance_opportunity_directions({}, {"SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "opportunity_phase": "LATE_OPPORTUNITY"}}, leader="SELL")
    sell = result["opportunities"]["SELL"]
    assert sell["opportunity_speed"] == "SLOW"
    assert sell["confirmation_window"] == "NEW_CAUSAL_EVENT"
    assert sell["wait_for"] == "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT"
    assert sell["chase_prohibited"] is True
    assert result["trade_authorized"] is False


def test_current_with_timing_preserves_production_tuple_contract_and_five_arg_boundary():
    class Pipeline:
        pass

    pipeline = Pipeline()
    calls = []

    def original_current(results, decision, gate_passed, candle):
        calls.append((results, decision, gate_passed, candle))
        return ({"BUY": {"direction": "BUY"}, "SELL": {"direction": "SELL"}}, "BUY", "CONTESTED")

    def original_advance(previous, current_by_direction, *, leader="NEUTRAL", competition="UNCONTESTED"):
        return {"opportunities": current_by_direction, "leader": leader, "competition": competition}

    pipeline._directional_lifecycle_current = original_current
    pipeline.advance_opportunity_directions = original_advance
    opportunity_lifecycle_timing.install(pipeline)

    result = pipeline._directional_lifecycle_current(
        {"E6": type("E6", (), {"output": {"direction": "BUY", "opportunity_phase": "EARLY_OPPORTUNITY", "opportunity_speed": "FAST"}})()},
        "NO_TRADE",
        False,
        "2026-09-07T04:50:00Z",
        {"event_id": "evt-1"},
    )

    assert len(calls) == 1
    assert calls[0][-1] == "2026-09-07T04:50:00Z"
    current, leader, competition = result
    assert leader == "BUY"
    assert competition == "CONTESTED"
    assert current["BUY"]["opportunity_speed"] == "FAST"
    assert current["BUY"]["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"


def test_progression_does_not_downgrade_early_fast_to_generic_confirmed_wait():
    progressed = advance_lifecycle_stage(
        {},
        {
            "candidate": True,
            "direction": "BUY",
            "opportunity_phase": "EARLY_OPPORTUNITY",
            "opportunity_speed": "FAST",
            "confirmation_window": "NEXT_CLOSED_M5_CANDLE",
            "wait_for": "FAST_CLOSED_CANDLE_CONFIRMATION",
            "chase_prohibited": False,
            "candle": "2026-09-07T05:35:00+07:00",
            "event_id": "evt-early-1",
        },
    )
    assert progressed["lifecycle_stage"] == "WATCH"
    assert progressed["opportunity_phase"] == "EARLY_OPPORTUNITY"
    assert progressed["opportunity_speed"] == "FAST"
    assert progressed["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"
    assert progressed["wait_for_stage"] == "FAST_CLOSED_CANDLE_CONFIRMATION"
    assert progressed["trade_authorized"] is False


def test_progression_propagates_early_standard_closed_candle_confirmation():
    progressed = advance_lifecycle_stage(
        {},
        {
            "candidate": True,
            "direction": "BUY",
            "opportunity_phase": "EARLY_OPPORTUNITY",
            "opportunity_speed": "STANDARD",
            "confirmation_window": "NEXT_CLOSED_M5_CANDLE",
            "wait_for": "CLOSED_CANDLE_CONFIRMATION",
            "candle": "2026-09-07T05:35:00+07:00",
            "event_id": "evt-early-2",
        },
    )
    assert progressed["lifecycle_stage"] == "WATCH"
    assert progressed["wait_for_stage"] == "CLOSED_CANDLE_CONFIRMATION"
    assert progressed["opportunity_phase"] == "EARLY_OPPORTUNITY"
    assert progressed["opportunity_speed"] == "STANDARD"


def test_progression_propagates_late_no_chase_boundary():
    progressed = advance_lifecycle_stage(
        {},
        {
            "candidate": True,
            "direction": "SELL",
            "opportunity_phase": "LATE_OPPORTUNITY",
            "opportunity_speed": "SLOW",
            "confirmation_window": "NEW_CAUSAL_EVENT",
            "wait_for": "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT",
            "chase_prohibited": True,
            "candle": "2026-09-07T05:35:00+07:00",
            "event_id": "evt-late-1",
        },
    )
    assert progressed["lifecycle_stage"] == "WATCH"
    assert progressed["opportunity_phase"] == "LATE_OPPORTUNITY"
    assert progressed["opportunity_speed"] == "SLOW"
    assert progressed["confirmation_window"] == "NEW_CAUSAL_EVENT"
    assert progressed["wait_for_stage"] == "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT"
    assert progressed["chase_prohibited"] is True
    assert progressed["trade_authorized"] is False


def test_opposite_direction_rejects_stale_opportunity_id_and_builds_new_identity():
    progressed = advance_lifecycle_stage(
        {"opportunity_id": "SELL|OPPORTUNITY_WATCH|old-event", "direction": "SELL"},
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "OPPORTUNITY_WATCH",
            "opportunity_id": "SELL|OPPORTUNITY_WATCH|old-event",
            "event_id": "buy-event-1",
            "candle": "2026-09-07T05:55:00Z",
        },
    )
    assert progressed["direction"] == "BUY"
    assert progressed["opportunity_id"] == "BUY|OPPORTUNITY_WATCH|buy-event-1"
    assert not progressed["opportunity_id"].startswith("SELL|")


def test_same_direction_new_causal_event_creates_new_opportunity_identity():
    progressed = advance_lifecycle_stage(
        {
            "opportunity_id": "BUY|OPPORTUNITY_WATCH|old-event",
            "direction": "BUY",
            "event_id": "old-event",
            "origin_event_id": "old-event",
            "lifecycle_stage": "WATCH",
        },
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "OPPORTUNITY_WATCH",
            "event_id": "new-event",
            "origin_event_id": "new-event",
            "candle": "2026-09-07T05:55:00Z",
        },
    )
    assert progressed["opportunity_id"] == "BUY|OPPORTUNITY_WATCH|new-event"
    assert progressed["event_id"] == "new-event"
    assert progressed["origin_event_id"] == "new-event"


def test_same_direction_same_causal_event_keeps_existing_identity():
    progressed = advance_lifecycle_stage(
        {
            "opportunity_id": "BUY|OPPORTUNITY_WATCH|same-event",
            "direction": "BUY",
            "event_id": "same-event",
            "origin_event_id": "same-event",
            "lifecycle_stage": "WATCH",
        },
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "OPPORTUNITY_WATCH",
            "event_id": "same-event",
            "candle": "2026-09-07T05:55:00Z",
        },
    )
    assert progressed["opportunity_id"] == "BUY|OPPORTUNITY_WATCH|same-event"
    assert progressed["origin_event_id"] == "same-event"
