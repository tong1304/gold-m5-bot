from production_v2.contracts import EngineResult
from production_v2 import e6_brain


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, None, 70.0, output, ())


def _pending_counterflow_fixture():
    return {
        "E1": _engine("E1", {"directional_pressure": "BEARISH"}),
        "E2": _engine("E2", {
            "finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.",
            "direction": "NEUTRAL",
            "opportunity_state": "EMERGING",
        }),
        "E3": _engine("E3", {
            "external_state": "MIXED",
            "internal_state": "DOWN",
        }),
        "E4": _engine("E4", {
            "event": "LOW_FAILED_BREAK_RECLAIM",
            "finding": "LOW_FAILED_BREAK_RECLAIM",
            "auction_state": "PENDING",
            "response_actor": "BUYERS",
            "liquidity_taker": "SELLERS",
            "event_id": "2026-09-03T10:50:00Z|LOW_FAILED_BREAK_RECLAIM|LOW|4425.23000000|UP",
        }),
        "E5": _engine("E5", {
            "finding": "FAVORABLE_LOCATION",
            "value_state": "EQUILIBRIUM",
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_long": 0.2176,
            "available_space_atr_short": 0.6442,
        }),
    }


def test_runtime_e6_chain_preserves_pending_opportunity_watch():
    result = e6_brain.analyze_e6({"bars": [], "symbol": "XAU/USD", "timeframe": "M5"}, _pending_counterflow_fixture())
    assert result.output["setup"] in {"OPPORTUNITY_WATCH", "OPPORTUNITY_THESIS"}
    assert result.output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert result.output["direction"] in {"BUY", "SELL"}
    assert result.output["watch_only"] is True
    assert result.output["trade_ready"] is False
    assert result.output["gate_passed"] is False
    assert "E4_AUCTION_FOLLOW_THROUGH" in result.output["missing_proof"]
    assert "NO_CAUSAL_OPPORTUNITY" not in result.output["reason_codes"]
