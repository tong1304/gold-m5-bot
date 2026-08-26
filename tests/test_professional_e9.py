from production_v2.contracts import EngineResult
from production_v2.professional_brain import run_professional_e9


def result(engine_id, direction=None, text="", score=80, output_extra=None):
    output = {"professional_reasoning": {"conclusion": text}}
    if direction is not None:
        output["direction"] = direction
    if output_extra:
        output.update(output_extra)
    return EngineResult(engine_id, engine_id, None, score, output, ())


def _buy_trade_plan():
    return {
        "trade_plan": {
            "direction": "BUY",
            "entry": 100.0,
            "stop_loss": 99.0,
            "take_profit_1": 101.5,
            "take_profit_2": 102.0,
            "rr_tp2": 2.0,
            "verified": True,
        },
        "risk_gate": "RISK_READY",
    }


def test_e9_does_not_use_upstream_vote_count_as_trade_decision():
    upstream = [
        result("E1", "BUY"), result("E2", "BUY"), result("E3", "BUY"),
        result("E4", "BUY"), result("E5", "BUY"), result("E6", "BUY"),
        result("E7", "BUY"), result("E8", "BUY"),
    ]
    e9 = run_professional_e9({}, upstream)
    assert e9.output["decision"] == "NO_TRADE"
    assert "SETUP_NOT_MATURE" in e9.reason_codes
    assert "ENTRY_CONFIRMATION_NOT_PROVEN" in e9.reason_codes
    assert "E8_TRADE_PLAN_INCOMPLETE" in e9.reason_codes


def test_e9_approves_confirmed_asymmetric_thesis():
    upstream = [
        result("E1", "BUY", "TREND_UP"),
        result("E2", "BUY", "OPPORTUNITY"),
        result("E3", "BUY", "BOS STRUCTURE"),
        result("E4", "BUY", "LIQUIDITY SWEEP RECLAIM"),
        result("E5", "BUY", "ADVANTAGEOUS DISCOUNT"),
        result("E6", "BUY", "MATURE CONTINUATION_SETUP"),
        result("E7", "BUY", "CONFIRMED TRIGGER_OBSERVED FOLLOW_THROUGH"),
        result("E8", "BUY", "ATTRACTIVE RR_OK POSITIVE_EXPECTANCY", output_extra=_buy_trade_plan()),
    ]
    e9 = run_professional_e9({}, upstream)
    assert e9.output["decision"] == "BUY"
    assert e9.output["professional_reasoning"]["execution_ready"] is True
    assert e9.output["decision_authority"] == "E9"


def test_e9_detects_structure_confirmation_conflict():
    upstream = [
        result("E1", "BUY", "TREND_UP"),
        result("E2", "BUY", "OPPORTUNITY"),
        result("E3", "SELL", "BEARISH STRUCTURE"),
        result("E4", "BUY", "LIQUIDITY SWEEP"),
        result("E5", "BUY", "ADVANTAGEOUS DISCOUNT"),
        result("E6", "BUY", "MATURE CONTINUATION_SETUP"),
        result("E7", "SELL", "CONFIRMED"),
        result("E8", "BUY", "ATTRACTIVE RR_OK", output_extra=_buy_trade_plan()),
    ]
    e9 = run_professional_e9({}, upstream)
    assert e9.output["decision"] == "NO_TRADE"
    assert "E1_E3_DIRECTION_CONFLICT" in e9.reason_codes
    assert "E6_E7_DIRECTION_CONFLICT" in e9.reason_codes


def test_e9_hard_invalidation_overrides_positive_evidence():
    upstream = [
        result("E1", "BUY", "TREND_UP"),
        result("E2", "BUY", "OPPORTUNITY"),
        result("E3", "BUY", "BOS STRUCTURE"),
        result("E4", "BUY", "LIQUIDITY SWEEP"),
        result("E5", "BUY", "ADVANTAGEOUS DISCOUNT"),
        result("E6", "BUY", "MATURE CONTINUATION_SETUP"),
        result("E7", "BUY", "CONFIRMED TRIGGER_OBSERVED"),
        result("E8", "BUY", "ATTRACTIVE RR_OK INVALID_RISK_GEOMETRY", output_extra=_buy_trade_plan()),
    ]
    e9 = run_professional_e9({}, upstream)
    assert e9.output["decision"] == "NO_TRADE"
    assert "E8_RISK_GEOMETRY_INVALID" in e9.reason_codes
    assert e9.output["professional_reasoning"]["execution_ready"] is True
