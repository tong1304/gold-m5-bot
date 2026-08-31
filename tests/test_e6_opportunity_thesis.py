from production_v2.e6_brain import analyze_e6
from production_v2.contracts import EngineResult


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def _bars(n=200):
    return [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5}
        for _ in range(n)
    ]


def _btc_like_upstream():
    return {
        "E1": _engine("E1", {
            "finding": "MARKET_STATE=RANGE; PRESSURE=UP; STRUCTURE=BULLISH",
            "pressure": "UP", "trend_state": "NONE", "market_state": "RANGE",
        }),
        "E2": _engine("E2", {
            "finding": "UP opportunity is developing based on closed-candle evidence.",
            "opportunity_state": "DEVELOPING", "opportunity_maturity": "DEVELOPING",
        }),
        "E3": _engine("E3", {
            "finding": "BOS_UP", "internal_state": "UP", "external_state": "UP",
            "bos": "BOS_UP", "lifecycle": "BOS_UP", "invalidation": "NO_INVALIDATION",
        }),
        "E4": _engine("E4", {
            "finding": "HIGH_ACCEPTANCE_CANDIDATE", "event": "HIGH_ACCEPTANCE_CANDIDATE",
            "auction_state": "PENDING", "event_age_bars": 0, "event_level": 105.0,
            "event_id": "test-event", "direction": "UP",
        }),
        "E5": _engine("E5", {
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_long": 0.54, "available_space_atr_short": 0.81,
            "value_response": "REJECTED_ABOVE_VALUE", "repricing_state": "REPRICING_FAILED",
        }),
    }


def test_e6_forms_breakout_retest_before_e2_confirmation():
    result = analyze_e6({"bars": _bars()}, _btc_like_upstream())
    assert result.output["setup"] == "BREAKOUT_RETEST"
    assert result.output["direction"] == "BUY"
    assert result.output["setup_exists"] is True
    assert result.output["state"] == "FORMING"
    assert result.output["trade_ready"] is False
    assert "E2_CLOSED_CANDLE_OPPORTUNITY_CONFIRMATION" in result.output["missing_proof"]
    assert "CLOSED_CANDLE_AUCTION_FOLLOW_THROUGH" in result.output["missing_proof"]
    assert result.output["reasoning_trace"]["decision"] == "FORM_OPPORTUNITY_THESIS_NOT_TRADE"


def test_e6_space_constraint_does_not_delete_thesis():
    upstream = _btc_like_upstream()
    upstream["E5"] = _engine("E5", {
        "structural_location": "INSIDE_STRUCTURE",
        "available_space_atr_long": 0.20,
        "available_space_atr_short": 0.80,
    })
    result = analyze_e6({"bars": _bars()}, upstream)
    assert result.output["setup_exists"] is True
    assert result.output["setup"] == "BREAKOUT_RETEST"
    assert "STRUCTURAL_SPACE_0.75_ATR_OR_VALID_TRADE_GEOMETRY" in result.output["missing_proof"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in result.output["counter_evidence"]


def test_e6_does_not_invent_setup_without_causal_chain():
    upstream = _btc_like_upstream()
    upstream["E3"] = _engine("E3", {
        "finding": "STRUCTURE_TRANSITION", "internal_state": "NEUTRAL", "external_state": "NEUTRAL",
        "bos": "NO_BREAK", "lifecycle": "TRANSITION", "invalidation": "NO_INVALIDATION",
    })
    upstream["E4"] = _engine("E4", {
        "finding": "HIGH_ACCEPTANCE_CANDIDATE", "event": "HIGH_ACCEPTANCE_CANDIDATE",
        "auction_state": "PENDING", "event_age_bars": 0, "direction": "UP",
    })
    result = analyze_e6({"bars": _bars()}, upstream)
    assert result.output["setup_exists"] is False
    assert result.output["setup"] == "NONE"
