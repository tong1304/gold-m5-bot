from production_v2.contracts import EngineResult
from production_v2.e9_brain import analyze_e9


def _r(engine_id, output=None, reasons=(), score=80):
    return EngineResult(engine_id, engine_id, None, score, output or {}, tuple(reasons))


def _plan(direction="SELL"):
    return {
        "direction": direction,
        "entry": 100.0,
        "stop_loss": 99.0 if direction == "BUY" else 101.0,
        "take_profit_1": 101.0 if direction == "BUY" else 99.0,
        "take_profit_2": 102.0 if direction == "BUY" else 98.0,
        "valid": True,
        "verified": True,
    }


def _upstream(e6_direction="SELL", e8_reasons=()):
    return {
        f"E{i}": _r(f"E{i}", {"finding": "SUPPORTIVE", "direction": "BUY"})
        for i in range(1, 6)
    } | {
        "E6": _r("E6", {"finding": f"{e6_direction} MATURE", "direction": e6_direction, "setup": "VALID_SETUP", "maturity": "MATURE"}),
        "E7": _r("E7", {"finding": f"{e6_direction} CONFIRMED", "direction": e6_direction, "confirmation": "CONFIRMED", "trigger_observed": True}),
        "E8": _r("E8", {"finding": "RISK_READY", "risk_gate": "RISK_READY", "trade_plan": _plan(e6_direction)}, reasons=e8_reasons),
    }


def test_e9_direction_is_owned_by_e6_thesis_not_upstream_vote_count():
    result = analyze_e9({}, _upstream("SELL"))
    assert result.output["direction"] == "SELL"
    assert result.output["decision"] == "SELL"


def test_e9_engine_result_economic_veto_cannot_be_hidden_from_output():
    result = analyze_e9({}, _upstream("SELL", ("REAL_RR_BELOW_MINIMUM",)))
    assert result.output["decision"] == "NO_TRADE"
    assert "REAL_RR_BELOW_MINIMUM" in result.reason_codes
