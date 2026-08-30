from production_v2.contracts import EngineResult
from production_v2.e9_brain import analyze_e9
from production_v2.pipeline import _prepare_e9_boundary


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", ())))


def _upstream():
    return {
        "E1": _engine("E1", {"market_state": "TREND_UP", "trend_state": "UP", "pressure": "UP", "structure": "BULLISH"}),
        "E2": _engine("E2", {"finding": "CONDITIONAL"}),
        "E3": _engine("E3", {"finding": "STRUCTURE_FORMING", "external_state": "MIXED", "internal_state": "UP", "lifecycle": "FORMING"}),
        "E4": _engine("E4", {
            "event": {"type": "HIGH_ACCEPTANCE_CANDIDATE", "level": 78939.2},
            "auction_state": "PENDING",
            "liquidity_taker": "BUYERS",
            "response_actor": "BUYERS",
            "liquidity_type": "EQUAL_LIQUIDITY",
        }),
        "E5": _engine("E5", {"repricing_state": "ACCEPTANCE_ABOVE_VALUE"}),
        "E6": _engine("E6", {
            "finding": "BUY AUCTION_ACCEPTANCE_CONTINUATION is validating",
            "direction": "BUY",
            "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
            "maturity": "VALIDATING",
        }),
        "E7": _engine("E7", {
            "confirmation_state": "PENDING",
            "trigger_observed": False,
            "reason_codes": ("PROOF_GATES_INCOMPLETE",),
        }),
        "E8": _engine("E8", {
            "risk_state": "UNRESOLVED",
            "reason_codes": ("INVALID_TRADE_GEOMETRY",),
        }),
    }


def test_e9_boundary_scalarizes_structured_liquidity_event_and_preserves_detail():
    upstream = _upstream()

    _prepare_e9_boundary(upstream)

    assert upstream["E4"].output["event"] == "TYPE=HIGH_ACCEPTANCE_CANDIDATE LEVEL=78939.2"
    assert upstream["E4"].output["event_detail"] == {"type": "HIGH_ACCEPTANCE_CANDIDATE", "level": 78939.2}

    result = analyze_e9({}, upstream)

    assert result.engine_id == "E9"
    assert result.output["decision"] == "NO_TRADE"
    assert result.output["auction_event"] == "TYPE=HIGH_ACCEPTANCE_CANDIDATE LEVEL=78939.2"
