from .opportunity_lifecycle_progression import advance_lifecycle_stage
from .opportunity_lifecycle_progression_surgery import lifecycle_telemetry


def _advance(previous, **current):
    payload = {
        "direction": "BUY",
        "candidate": True,
        "ready": False,
        "thesis_proven": False,
        "invalidated": False,
        "candle": current.pop("candle", "2026-09-07T10:00:00Z"),
        "event_id": current.pop("event_id", "E1"),
        **current,
    }
    return advance_lifecycle_stage(previous, payload)


def test_opportunity_walks_watch_to_confirmed_to_e6_to_e7_to_e8_to_trade_across_closed_bars():
    state = _advance(None, candle="2026-09-07T10:00:00Z")
    assert state["lifecycle_stage"] == "WATCH"
    opportunity_id = state["opportunity_id"]
    state = _advance(state, candle="2026-09-07T10:05:00Z", confirmed=True, event_id="E2")
    assert state["lifecycle_stage"] == "CONFIRMED"
    assert state["opportunity_id"] == opportunity_id
    state = _advance(state, candle="2026-09-07T10:10:00Z", thesis_proven=True, event_id="E3")
    assert state["lifecycle_stage"] == "E6_THESIS"
    assert state["opportunity_id"] == opportunity_id
    state = _advance(state, candle="2026-09-07T10:15:00Z", thesis_proven=True, e7_confirmed=True, event_id="E4")
    assert state["lifecycle_stage"] == "E7_CONFIRMED"
    state = _advance(state, candle="2026-09-07T10:20:00Z", thesis_proven=True, e7_confirmed=True, e8_ready=True, event_id="E5")
    assert state["lifecycle_stage"] == "E8_READY"
    state = _advance(state, candle="2026-09-07T10:25:00Z", thesis_proven=True, e7_confirmed=True, e8_ready=True, e9_trade=True, ready=True, event_id="E6")
    assert state["lifecycle_stage"] == "TRADE"
    assert state["trade_authorized"] is True
    assert state["execution_state"] == "ALERT_READY"
    assert state["wait_for_stage"] == "USER_ACTION_REQUIRED"
    assert state["opportunity_id"] == opportunity_id
    assert state["event_id"] == "E6"
    assert state["origin_event_id"] == "E1"
    assert [item["stage"] for item in state["stage_history"]] == ["WATCH", "CONFIRMED", "E6_THESIS", "E7_CONFIRMED", "E8_READY", "TRADE"]


def test_waiting_between_stages_does_not_reset_the_same_opportunity():
    state = _advance(None, candle="2026-09-07T10:00:00Z")
    opportunity_id = state["opportunity_id"]
    state = _advance(state, candle="2026-09-07T10:05:00Z", confirmed=True)
    assert state["lifecycle_stage"] == "CONFIRMED"
    state = _advance(state, candle="2026-09-07T10:10:00Z")
    assert state["lifecycle_stage"] == "CONFIRMED"
    assert state["opportunity_id"] == opportunity_id
    assert state["wait_for_stage"] == "E6_THESIS"


def test_one_closed_candle_cannot_jump_multiple_proof_stages():
    state = _advance(None, candle="2026-09-07T10:00:00Z")
    state = _advance(state, candle="2026-09-07T10:05:00Z", confirmed=True, thesis_proven=True, e7_confirmed=True, e8_ready=True, e9_trade=True, ready=True)
    assert state["lifecycle_stage"] == "CONFIRMED"
    assert state["trade_authorized"] is False


def test_too_late_is_terminal_and_preserves_opportunity_identity():
    state = _advance(None, candle="2026-09-07T10:00:00Z")
    opportunity_id = state["opportunity_id"]
    state = _advance(state, candle="2026-09-07T10:05:00Z", execution_state="TOO_LATE")
    assert state["lifecycle_stage"] == "TOO_LATE"
    assert state["state"] == "EXPIRED"
    assert state["trade_authorized"] is False
    assert state["opportunity_id"] == opportunity_id


def test_expired_is_terminal_and_does_not_reopen_without_new_event():
    state = _advance(None, candle="2026-09-07T10:00:00Z")
    opportunity_id = state["opportunity_id"]
    state = _advance(state, candle="2026-09-07T10:05:00Z", execution_state="EXPIRED")
    assert state["lifecycle_stage"] == "EXPIRED"
    assert state["trade_authorized"] is False
    state = _advance(state, candle="2026-09-07T10:10:00Z", thesis_proven=True, ready=True, e9_trade=True)
    assert state["lifecycle_stage"] == "EXPIRED"
    assert state["opportunity_id"] == opportunity_id
    assert state["trade_authorized"] is False


def test_invalidated_is_terminal_and_records_reason():
    state = _advance(None, candle="2026-09-07T10:00:00Z")
    state = _advance(state, candle="2026-09-07T10:05:00Z", invalidated=True, invalidation_reason="STRUCTURE_INVALIDATED")
    assert state["lifecycle_stage"] == "INVALIDATED"
    assert state["state"] == "INVALIDATED"
    assert state["trade_authorized"] is False
    assert state["invalidation_reason"] == "STRUCTURE_INVALIDATED"


def test_lifecycle_telemetry_is_machine_readable_and_keeps_wait_and_terminal_fields():
    line = lifecycle_telemetry("BTC", {"opportunity_id": "BUY|TREND|E4-22", "origin_event_id": "E4-22", "event_id": "E4-23", "last_evaluated_candle": "2026-09-07T10:05:00Z", "lifecycle_stage": "E7_CONFIRMED", "state": "WAITING", "wait_for_stage": "E8_READY", "terminal_stage": None, "trade_authorized": False})
    assert line.startswith("[PRODUCTION V2] OPPORTUNITY_LIFECYCLE")
    assert "symbol=BTC" in line
    assert "opportunity_id=BUY|TREND|E4-22" in line
    assert "origin_event_id=E4-22" in line
    assert "event_id=E4-23" in line
    assert "stage=E7_CONFIRMED" in line
    assert "wait_for=E8_READY" in line
    assert "terminal=NONE" in line
    assert "trade_authorized=0" in line
