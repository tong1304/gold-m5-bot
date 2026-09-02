from production_v2.brain_handoff import build_handoff, build_lifecycle


def test_handoff_preserves_upstream_evidence_and_authority_boundary():
    upstream = {
        "E1": {"market_state": "TRANSITION", "direction": "SELL", "reason_codes": ["PRESSURE_DOWN"]},
        "E2": {"opportunity_state": "DEVELOPING", "direction": "SELL", "missing": ["FOLLOW_THROUGH"]},
    }
    packet = build_handoff("E3", {"finding": "STRUCTURE_FORMING", "direction": "SELL"}, upstream)
    assert packet["engine"] == "E3"
    assert packet["upstream"]["E1"]["market_state"] == "TRANSITION"
    assert packet["upstream"]["E2"]["missing"] == ["FOLLOW_THROUGH"]
    assert packet["authority"] == "E3_OWN_SCOPE_ONLY"
    assert packet["must_not_rewrite_upstream"] is True


def test_handoff_exposes_next_event_and_lifecycle_state():
    packet = build_handoff(
        "E4",
        {
            "direction": "SELL",
            "auction_state": "PENDING",
            "opportunity_next_event": "RECLAIM_AND_FOLLOW_THROUGH",
            "opportunity_stage": "AUCTION_PENDING",
        },
        {"E1": {"direction": "SELL"}, "E3": {"direction": "SELL"}},
    )
    assert packet["stage"] == "AUCTION_PENDING"
    assert packet["next_required_event"] == "RECLAIM_AND_FOLLOW_THROUGH"
    assert packet["direction"] == "SELL"


def test_lifecycle_keeps_pending_opportunity_alive_until_invalidated():
    results = {
        "E1": {"opportunity_direction": "SELL", "opportunity_state": "VISIBLE_PENDING_PROOF", "opportunity_stage": "STATE_ESTABLISHED"},
        "E2": {"opportunity_direction": "SELL", "opportunity_state": "VISIBLE_PENDING_PROOF", "opportunity_stage": "REGIME_DEVELOPING", "opportunity_next_event": "REGIME_ACCEPTANCE_AND_FOLLOW_THROUGH"},
        "E4": {"opportunity_direction": "SELL", "opportunity_state": "VISIBLE_PENDING_PROOF", "opportunity_stage": "AUCTION_PENDING", "opportunity_next_event": "RECLAIM_AND_FOLLOW_THROUGH"},
        "E5": {"opportunity_direction": "SELL", "opportunity_state": "VISIBLE_BUT_BLOCKED", "opportunity_stage": "FORMING", "opportunity_next_event": "PRICE_RESPONSE_AT_VALUE_OR_STRUCTURE"},
        "E6": {"opportunity_direction": "NEUTRAL", "opportunity_state": "NO_EDGE", "opportunity_stage": "NO_SETUP"},
    }
    lifecycle = build_lifecycle(results)
    assert lifecycle["state"] == "WAITING"
    assert lifecycle["direction"] == "SELL"
    assert lifecycle["next_required_event"] in {"RECLAIM_AND_FOLLOW_THROUGH", "PRICE_RESPONSE_AT_VALUE_OR_STRUCTURE", "REGIME_ACCEPTANCE_AND_FOLLOW_THROUGH"}
    assert lifecycle["trade_authorized"] is False
