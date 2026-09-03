from production_v2.bootstrap_surgery import _rescue_e6_causal_candidate
from production_v2.contracts import EngineResult


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def test_high_acceptance_candidate_creates_e6_watch_even_when_space_is_pending():
    original = _engine("E6", {"setup_exists": False, "state": "NO_SETUP", "finding": "No causal setup"})
    upstream = {
        "E1": _engine("E1", {"pressure": "UP", "directional_pressure": "UP"}),
        "E2": _engine("E2", {"finding": "UP opportunity is confirmed"}),
        "E3": _engine("E3", {"internal_state": "UP", "external_state": "MIXED", "finding": "STRUCTURE_FORMING"}),
        "E4": _engine("E4", {"event": "HIGH_ACCEPTANCE_CANDIDATE", "liquidity_taker": "BUYERS", "auction_state": "PENDING"}),
        "E5": _engine("E5", {"finding": "FAVORABLE_LOCATION", "structural_location": "AT_RESISTANCE", "value_state": "PREMIUM", "available_space_atr_long": None}),
    }

    result = _rescue_e6_causal_candidate(original, upstream)

    assert result.output["setup_exists"] is True
    assert result.output["setup"] == "AUCTION_ACCEPTANCE_CONTINUATION"
    assert result.output["direction"] == "BUY"
    assert result.output["trade_ready"] is False
    assert "E5_SPACE_PENDING_TRADE_ECONOMICS" in result.output["reason_codes"]


def test_high_rejection_keeps_space_as_trade_constraint_not_thesis_veto():
    original = _engine("E6", {"setup_exists": False, "state": "NO_SETUP"})
    upstream = {
        "E1": _engine("E1", {"pressure": "DOWN"}),
        "E2": _engine("E2", {"finding": "SELL opportunity is developing"}),
        "E3": _engine("E3", {"internal_state": "DOWN", "external_state": "DOWN", "finding": "BEARISH_STRUCTURE"}),
        "E4": _engine("E4", {"event": "HIGH_SWEEP_REJECTION", "liquidity_taker": "BUYERS", "response_actor": "SELLERS", "auction_state": "PENDING"}),
        "E5": _engine("E5", {"finding": "FAVORABLE_LOCATION", "structural_location": "AT_RESISTANCE", "value_state": "PREMIUM", "available_space_atr_short": 0.40}),
    }

    result = _rescue_e6_causal_candidate(original, upstream)

    assert result.output["setup_exists"] is True
    assert result.output["setup"] == "LIQUIDITY_REVERSAL"
    assert result.output["direction"] == "SELL"
    assert result.output["space_diagnostic"]["space_sufficient"] is False
    assert result.output["trade_ready"] is False
