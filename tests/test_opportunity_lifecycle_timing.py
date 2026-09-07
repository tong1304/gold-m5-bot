from production_v2 import opportunity_lifecycle_timing


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


def test_current_with_timing_accepts_pipeline_five_arg_boundary_without_breaking_legacy_helper():
    class Pipeline:
        pass

    pipeline = Pipeline()
    calls = []

    def original_current(results, decision, gate_passed, candle):
        calls.append((results, decision, gate_passed, candle))
        return {"BUY": {"direction": "BUY"}, "SELL": {"direction": "SELL"}}

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
    assert result["BUY"]["opportunity_speed"] == "FAST"
    assert result["BUY"]["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"
