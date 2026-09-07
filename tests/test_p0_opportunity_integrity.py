from types import SimpleNamespace

from production_v2 import p0_opportunity_integrity as integrity


def _pipeline():
    pipeline = SimpleNamespace()

    def directional(results, decision, gate_passed, candle, causal_anchor=None):
        return (
            {
                "BUY": {"candidate": False, "direction": "BUY", "setup": "OPPORTUNITY_WATCH"},
                "SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "event_id": "stale-sell-event", "wait_for": ["E6_CAUSAL_SETUP_PROOF"]},
            },
            "SELL",
            "UNCONTESTED",
        )

    def lifecycle(previous, current_by_direction, *, leader="NEUTRAL", competition="UNCONTESTED"):
        return {
            "opportunities": {
                d: {"state": "WATCHING" if c.get("candidate") else "IDLE", "direction": d, "opportunity_id": c.get("event_id")}
                for d, c in current_by_direction.items()
            },
            "leader": leader,
            "competition": competition,
            "active_directions": [d for d, c in current_by_direction.items() if c.get("candidate")],
            "state": "WATCHING",
            "trade_authorized": False,
        }

    pipeline._directional_lifecycle_current = directional
    pipeline.advance_opportunity_directions = lifecycle
    return pipeline


def test_e6_buy_canonicalizes_direction_event_and_wait_window():
    pipeline = _pipeline()
    integrity.install(pipeline)
    results = {
        "E4": SimpleNamespace(output={"event_id": "buy-event-9"}),
        "E6": SimpleNamespace(output={"direction": "BUY", "candidate_type": "EARLY_OPPORTUNITY_CANDIDATE", "opportunity_phase_speed": "EARLY_OPPORTUNITY", "wait_for": "CLOSED_CANDLE_CONFIRMATION"}),
        "E2": SimpleNamespace(output={"opportunity_book": {"candidates": []}}),
    }
    current, leader, _ = pipeline._directional_lifecycle_current(results, "NO_TRADE", False, "c9", {})
    assert current["BUY"]["candidate"] is True
    assert current["BUY"]["event_id"] == "buy-event-9"
    assert current["BUY"]["wait_for"] == "CLOSED_CANDLE_CONFIRMATION"
    assert current["SELL"]["event_id"] is None
    assert leader == "BUY"


def test_e6_watch_repairs_idle_lifecycle_on_real_production_callable():
    pipeline = _pipeline()
    integrity.install(pipeline)
    current = {
        "BUY": {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "event_id": "evt-buy", "candle": "c10"},
        "SELL": {"candidate": False, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "candle": "c10"},
    }
    lifecycle = pipeline.advance_opportunity_directions({}, current, leader="BUY", competition="UNCONTESTED")
    assert lifecycle["opportunities"]["BUY"]["state"] == "WATCHING"
    assert lifecycle["active_directions"] == ["BUY"]
    assert lifecycle["p0_integrity"]["single_production_lifecycle_path"] is True


def test_real_production_callable_promotes_to_trade_when_all_gates_are_proven():
    pipeline = _pipeline()
    integrity.install(pipeline)
    current = {
        "BUY": {"candidate": True, "direction": "BUY", "setup": "LIQUIDITY_RESPONSE", "event_id": "evt-42", "origin_event_id": "evt-42", "candle": "c42", "confirmed": True, "e4_state": "CONFIRMED", "thesis_proven": True, "e7_confirmed": True, "e7_confirmation_state": "TRIGGER_CONFIRMED", "e8_ready": True, "e9_trade": True},
        "SELL": {"candidate": False, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "candle": "c42"},
    }
    result = pipeline.advance_opportunity_directions({"opportunities": {"BUY": {"opportunity_id": "BUY|OPPORTUNITY_WATCH|evt-42", "direction": "BUY", "state": "WATCHING", "lifecycle_stage": "WATCH"}}}, current, leader="BUY")
    assert result["opportunities"]["BUY"]["lifecycle_stage"] == "TRADE"
    assert result["opportunities"]["BUY"]["trade_authorized"] is True


def test_direction_change_gets_new_identity_instead_of_reusing_old_direction():
    pipeline = _pipeline()
    integrity.install(pipeline)
    previous = {"opportunities": {"SELL": {"opportunity_id": "SELL|OPPORTUNITY_WATCH|evt-old", "direction": "SELL", "state": "WATCHING", "setup": "OPPORTUNITY_WATCH", "event_id": "evt-old"}}}
    current = {
        "BUY": {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "event_id": "evt-new", "candle": "c-new"},
        "SELL": {"candidate": False, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "candle": "c-new"},
    }
    result = pipeline.advance_opportunity_directions(previous, current, leader="BUY")
    assert result["opportunities"]["BUY"]["opportunity_id"] == "BUY|OPPORTUNITY_WATCH|evt-new"
    assert result["opportunities"]["BUY"]["opportunity_id"] != "SELL|OPPORTUNITY_WATCH|evt-old"
