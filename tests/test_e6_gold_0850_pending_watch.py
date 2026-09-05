from production_v2 import pipeline as pipeline_module
from production_v2.contracts import EngineResult
from production_v2.e6_pending_event_surgery import install

install(pipeline_module)


def _r(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def test_gold_0850_pending_high_failed_break_reclaim_survives_as_sell_watch():
    upstream = {
        "E1": _r("E1", {"directional_pressure": "BALANCED", "pressure": "BALANCED", "structure": "BULLISH"}),
        "E2": _r("E2", {"finding": "NEUTRAL opportunity is unproven based on closed-candle evidence."}),
        "E3": _r("E3", {"external_state": "UP", "internal_state": "UP", "protected_integrity": "VALID", "protected_completeness": "COMPLETE"}),
        "E4": _r("E4", {"event": "HIGH_FAILED_BREAK_RECLAIM", "finding": "HIGH_FAILED_BREAK_RECLAIM", "event_id": "2026-09-03T08:50:00Z|HIGH_FAILED_BREAK_RECLAIM|HIGH|4435.59|DOWN", "response_actor": "SELLERS", "liquidity_taker": "BUYERS", "auction_state": "PENDING", "liquidity_externality": "INTERNAL"}),
        "E5": _r("E5", {"finding": "ACCEPTED_AUCTION_NO_REVERSAL_EDGE", "value_state": "EQUILIBRIUM", "structural_location": "INSIDE_STRUCTURE", "available_space_atr_long": 0.6238425926, "available_space_atr_short": 0.7111625514}),
    }
    out = pipeline_module.analyze_e6([], upstream).output
    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert out["direction"] == "SELL"
    assert out["watch_only"] is True
    assert out["trade_ready"] is False
    assert out["gate_passed"] is False
    assert "NO_CAUSAL_OPPORTUNITY" not in set(out.get("reason_codes", []))
    assert "E4_AUCTION_FOLLOW_THROUGH" in set(out["missing_proof"])
    assert "E7_CONFIRMATION" in set(out["missing_proof"])
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in set(out["missing_proof"])
    assert out["available_space_atr"] == 0.7112
