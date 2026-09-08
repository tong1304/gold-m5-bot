from production_v2.opportunity_core import OpportunityRecord, canonical_stage


def test_canonical_stage_maps_watch_and_waiting_to_distinct_states():
    assert canonical_stage({"state": "WATCHING", "setup": "OPPORTUNITY_WATCH"}) == "WATCH"
    assert canonical_stage({"state": "WAITING", "setup": "TREND"}) == "CONFIRMING"


def test_canonical_stage_maps_ready_and_e9_trade():
    lifecycle = {"state": "READY", "setup": "TREND", "opportunity_id": "BUY|TREND|E4-1"}
    assert canonical_stage(lifecycle) == "ACTIONABLE"
    assert canonical_stage(lifecycle, e9_decision="TRADE") == "TRADE"


def test_record_preserves_causal_anchor_and_required_fields():
    lifecycle = {
        "opportunity_id": "BUY|TREND|E4-1",
        "direction": "BUY",
        "setup": "TREND",
        "state": "WAITING",
        "bars_waited": 2,
        "origin_candle": "2026-09-08T10:00:00+00:00",
        "last_evaluated_candle": "2026-09-08T10:10:00+00:00",
        "causal_event_anchor": {"event_id": "E4-1", "event_candle": "2026-09-08T10:00:00+00:00"},
        "invalidation_reason": None,
    }
    record = OpportunityRecord.from_lifecycle(lifecycle, "XAUUSD", "M5")
    data = record.as_dict()
    assert data["opportunity_id"] == "BUY|TREND|E4-1"
    assert data["symbol"] == "XAUUSD"
    assert data["timeframe"] == "M5"
    assert data["event_anchor"]["event_id"] == "E4-1"
    assert data["age_bars"] == 2
    assert data["stage"] == "CONFIRMING"
    assert data["decision_authority"] == "E9_ONLY"


def test_record_exposes_edge_remaining_without_rewriting_lifecycle():
    lifecycle = {"opportunity_id": "SELL|TREND|E4-2", "direction": "SELL", "state": "READY"}
    record = OpportunityRecord.from_lifecycle(lifecycle, "XAUUSD", "M5", edge_remaining=0.42)
    assert record.edge_remaining == 0.42
    assert lifecycle["state"] == "READY"
