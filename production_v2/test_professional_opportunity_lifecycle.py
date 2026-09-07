from __future__ import annotations

from production_v2.professional_opportunity_controller import (
    canonical_event_clock,
    derive_opportunity_state,
)


def _base(*, event="LOW_SWEEP_REJECTION", direction="BUY", age=0, space=0.4):
    return {
        "candle": "2026-09-07T10:40:00+00:00",
        "e1": {"directional_pressure": "BEARISH"},
        "e2": {"direction": "SELL", "opportunity_state": "DEVELOPING"},
        "e3": {"external_state": "DOWN", "internal_state": "MIXED"},
        "e4": {
            "event": event,
            "event_id": "2026-09-07T10:30:00+00:00|LOW_SWEEP_REJECTION|HIGH|79420",
            "event_candle_id": "2026-09-07T10:30:00+00:00",
            "direction": direction,
            "event_age_bars": age,
            "auction_state": "PENDING",
        },
        "e5": {
            "available_space_atr_long": space,
            "available_space_atr_short": 1.3,
            "finding": "FAVORABLE_LOCATION",
        },
        "e6": {
            "direction": direction,
            "setup_exists": True,
            "e6_thesis_proven": True,
            "setup_family": "LIQUIDITY_REVERSAL",
            "thesis_status": "FORMING",
        },
        "e7": {"confirmation_state": "PENDING"},
        "e8": {"economic_state": "PRECHECK_PASS", "pre_economics": {"tradeable": True}},
        "e9": {"decision": "NO_TRADE", "trade_ready": False},
    }


def test_causal_event_direction_beats_background_trend_context():
    state = derive_opportunity_state(_base())
    assert state["direction"] == "BUY"
    assert state["stage"] in {"DETECTED", "WATCH", "THESIS_FORMED", "ARMED"}
    assert "E1_COUNTER_EVIDENCE" in state["counter_evidence"] or state["counter_evidence"]


def test_structural_space_constrains_tradeability_not_opportunity():
    state = derive_opportunity_state(_base(space=0.2))
    assert state["stage"] != "NO_OPPORTUNITY"
    assert state["tradeability"] == "CONSTRAINED"
    assert state["execution_authorized"] is False


def test_armed_is_not_execution_authorization():
    state = derive_opportunity_state(_base(space=1.2))
    assert state["stage"] == "ARMED"
    assert state["execution_authorized"] is False
    assert state["wait_for"]


def test_canonical_event_clock_ignores_inconsistent_nested_age():
    payload = _base(age=0)
    clock = canonical_event_clock(payload["e4"], payload["candle"])
    assert clock["age_bars"] == 2
    assert clock["event_candle"] == "2026-09-07T10:30:00+00:00"
