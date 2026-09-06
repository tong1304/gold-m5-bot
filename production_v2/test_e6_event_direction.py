from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6
from production_v2.opportunity_lifecycle import advance_opportunity


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", ())))


def test_unresolved_liquidity_interaction_does_not_invent_opposite_direction():
    upstream = {
        "E1": _engine("E1", {"directional_pressure": "BEARISH"}),
        "E2": _engine("E2", {"finding": "NEUTRAL", "opportunity_maturity": "UNRESOLVED"}),
        "E3": _engine("E3", {"external_state": "MIXED", "internal_state": "DOWN"}),
        "E4": _engine("E4", {
            "event": "HIGH_LIQUIDITY_INTERACTION",
            "auction_state": "PENDING",
            "liquidity_taker": "BUYERS",
            "response_actor": "UNCLEAR",
            "directional_implication": "NEUTRAL",
            "event_id": "evt-high-1",
        }),
        "E5": _engine("E5", {
            "finding": "REJECTED_BELOW_VALUE",
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_short": 0.0,
            "available_space_atr_long": 0.2,
        }),
    }
    result = analyze_e6({}, upstream)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["direction"] == "SELL"
    assert result.output["event_id"] == "evt-high-1"
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in result.output["missing_proof"]
    assert result.output["trade_ready"] is False


def test_legacy_watch_is_rekeyed_when_new_causal_event_arrives():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 2,
        "event_id": "",
        "origin_event_id": "",
        "origin_candle": "2026-09-06T07:25:00Z",
        "last_evaluated_candle": "2026-09-06T07:30:00Z",
    }
    current = {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "2026-09-06T07:30:00Z|HIGH_LIQUIDITY_INTERACTION|HIGH|79799.05000000|NEUTRAL",
        "candle": "2026-09-06T07:35:00Z",
        "candidate": True,
        "ready": False,
        "invalidated": False,
        "thesis_proven": False,
        "wait_for": ["E4_AUCTION_FOLLOW_THROUGH"],
    }
    result = advance_opportunity(previous, current)
    assert result["state"] == "REPLACED"
    assert result["previous_opportunity_id"] == "SELL|OPPORTUNITY_WATCH"
    assert result["opportunity_id"].startswith("SELL|OPPORTUNITY_WATCH|")
    assert result["event_id"] == current["event_id"]
    assert result["bars_waited"] == 0
