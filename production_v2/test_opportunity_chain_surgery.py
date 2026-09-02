from production_v2.bootstrap_surgery import _rescue_e6_causal_candidate, _gate_e8_applicability
from production_v2.contracts import EngineResult


def _result(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def test_failed_break_reclaim_can_form_causal_thesis_before_e2_confirmation():
    upstream = {
        "E1": _result("E1", {
            "finding": "MARKET_STATE=TRANSITION",
            "pressure": "DOWN",
            "directional_pressure": "DOWN",
            "trend_state": "NONE",
        }),
        "E2": _result("E2", {
            "finding": "DOWN opportunity is developing",
            "opportunity_state": "DEVELOPING",
            "opportunity_maturity": "DEVELOPING",
        }),
        "E3": _result("E3", {
            "finding": "FAILED_BOS",
            "internal_state": "MIXED",
            "external_state": "UP",
        }),
        "E4": _result("E4", {
            "event": "HIGH_FAILED_BREAK_RECLAIM",
            "direction": "DOWN",
            "auction_state": "PENDING",
            "event_level": 4314.44,
        }),
        "E5": _result("E5", {
            "finding": "FAVORABLE_LOCATION",
            "structural_location": "INSIDE_STRUCTURE",
            "value_state": "DISCOUNT",
            "value_response": "REJECTED_BELOW_VALUE",
            "available_space_atr_short": 2.0207,
            "available_space_atr_long": 2.1434,
        }),
    }

    original = _result("E6", {
        "state": "ABSENT",
        "setup_state": "ABSENT",
        "setup": "NONE",
        "direction": "SELL",
        "setup_exists": False,
        "finding": "No causal setup hypothesis survives current closed-candle evidence.",
        "reason_codes": ["CAUSAL_SETUP_PROOF_INCOMPLETE"],
        "space_diagnostic": {"available_space_atr": 2.0207, "space_sufficient": True},
    })

    result = _rescue_e6_causal_candidate(original, upstream)
    assert result.output["setup"] == "LIQUIDITY_REVERSAL"
    assert result.output["direction"] == "SELL"
    assert result.output["setup_exists"] is True
    assert result.output["state"] == "FORMING"
    assert result.output["trade_permission"] is False


def test_e8_is_not_applicable_without_surviving_e6_thesis():
    results = {
        "E6": _result("E6", {
            "setup_exists": False,
            "state": "ABSENT",
            "setup": "NONE",
            "direction": "NEUTRAL",
        }),
        "E8": _result("E8", {
            "state": "UNRESOLVED",
            "reasons": ["HISTORICAL_SAMPLE_INSUFFICIENT", "INVALID_TRADE_GEOMETRY"],
            "reason_codes": ["HISTORICAL_SAMPLE_INSUFFICIENT", "INVALID_TRADE_GEOMETRY"],
        }),
    }

    result = _gate_e8_applicability(results["E8"], results)
    assert result.output["state"] == "NOT_APPLICABLE"
    assert result.output["trade_plan_verified"] is False
    assert "E6_THESIS_REQUIRED" in result.output["reason_codes"]
