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


def test_e9_preserves_e6_candidate_identity_when_setup_is_only_in_finding():
    upstream = {
        "E1": _engine("E1", {"market_state": "TRANSITION", "structure": "BULLISH", "pressure": "DOWN"}),
        "E2": _engine("E2", {"finding": "NEUTRAL", "reason_codes": ("DIRECTIONAL_EDGE_NOT_ESTABLISHED",)}),
        "E3": _engine("E3", {"finding": "BULLISH_STRUCTURE", "lifecycle": "ESTABLISHED", "invalidation": "NO_INVALIDATION"}),
        "E4": _engine("E4", {"event": "HIGH_SWEEP_REJECTION", "auction_state": "PENDING", "liquidity_taker": "BUYERS", "response_actor": "SELLERS"}),
        "E5": _engine("E5", {"finding": "WAIT_CONFIRMATION", "structural_location": "INSIDE_STRUCTURE"}),
        "E6": _engine("E6", {
            "finding": "SELL LIQUIDITY_REVERSAL is a candidate hypothesis only; required upstream proof is incomplete.",
            "reason_codes": ("E2_OPPORTUNITY_UNRESOLVED", "SPACE_CONFLICT"),
            "maturity": "HYPOTHESIS",
        }),
        "E7": _engine("E7", {
            "finding": "The thesis remains a hypothesis; required proof is incomplete.",
            "reason_codes": ("PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING"),
        }),
        "E8": _engine("E8", {
            "risk_state": "UNRESOLVED",
            "reason_codes": ("INVALID_TRADE_GEOMETRY", "REAL_RR_BELOW_MINIMUM"),
        }),
    }

    result = analyze_e9({}, upstream)

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["thesis_state"] == "ESTABLISHED"
    assert result.output["setup_state"] == "HYPOTHESIS"
    assert result.output["execution_state"] == "BLOCKED"
    assert result.output["direction"] == "SELL"
    assert result.output["setup"] == "LIQUIDITY_REVERSAL"


def test_e9_candidate_identity_never_authorizes_trade_without_confirmation_and_risk():
    upstream = {
        "E1": _engine("E1", {"market_state": "TRANSITION", "structure": "BULLISH", "pressure": "DOWN"}),
        "E2": _engine("E2", {"finding": "NEUTRAL"}),
        "E3": _engine("E3", {"finding": "BULLISH_STRUCTURE", "lifecycle": "ESTABLISHED", "invalidation": "NO_INVALIDATION"}),
        "E4": _engine("E4", {"event": "HIGH_SWEEP_REJECTION", "auction_state": "PENDING"}),
        "E5": _engine("E5", {"finding": "WAIT_CONFIRMATION"}),
        "E6": _engine("E6", {
            "finding": "SELL LIQUIDITY_REVERSAL is a candidate hypothesis only; required upstream proof is incomplete.",
            "maturity": "HYPOTHESIS",
        }),
        "E7": _engine("E7", {"confirmation_state": "PENDING", "reason_codes": ("VALID_CLOSED_CANDLE_TRIGGER_MISSING",)}),
        "E8": _engine("E8", {"risk_state": "UNRESOLVED", "reason_codes": ("INVALID_TRADE_GEOMETRY",)}),
    }

    result = analyze_e9({}, upstream)

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["execution_state"] == "BLOCKED"
    assert result.output["direction"] == "SELL"
    assert result.output["setup"] == "LIQUIDITY_REVERSAL"
