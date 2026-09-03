from production_v2.contracts import EngineResult
from production_v2 import e6_brain


def _r(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, ())


def test_gold_0805_high_sweep_rejection_survives_as_sell_watch():
    upstream = {
        "E1": _r("E1", {
            "market_state": "RANGE",
            "directional_pressure": "UP",
            "structure": "BULLISH",
        }),
        "E2": _r("E2", {
            "finding": "NEUTRAL opportunity is unproven based on closed-candle evidence.",
            "counter_evidence": "DIRECTIONAL_EDGE_NOT_ESTABLISHED",
        }),
        "E3": _r("E3", {
            "external_state": "MIXED",
            "internal_state": "MIXED",
            "protected_integrity": "VALID",
            "protected_completeness": "NO_DIRECTIONAL_REGIME",
        }),
        "E4": _r("E4", {
            "event": "HIGH_SWEEP_REJECTION",
            "event_id": "GOLD-0805",
            "liquidity_taker": "BUYERS",
            "response_actor": "SELLERS",
            "liquidity_type": "EQUAL_LIQUIDITY",
            "liquidity_externality": "INTERNAL",
            "liquidity_proximity": "NEAR",
            "liquidity_quality": 70,
            "auction_quality": 56.53,
            "auction_information": "MEDIUM_INFORMATION",
            "auction_state": "PENDING",
        }),
        "E5": _r("E5", {
            "finding": "FAVORABLE_LOCATION",
            "value_state": "PREMIUM",
            "value_response": "REJECTED_ABOVE_VALUE",
            "repricing_state": "REPRICING_FAILED",
            "structural_location": "INSIDE_STRUCTURE",
            "next_resistance": 4438.635,
            "next_support": 4425.55,
            "available_space_atr_long": 0.5833333333,
            "available_space_atr_short": 1.5222988506,
        }),
    }

    result = e6_brain.analyze_e6({}, upstream)
    out = result.output

    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert out["direction"] == "SELL"
    assert out["watch_only"] is True
    assert out["trade_ready"] is False
    assert out["gate_passed"] is False
    assert "NO_CAUSAL_OPPORTUNITY" not in out.get("reason_codes", [])
    assert "E4_AUCTION_FOLLOW_THROUGH" in out["missing_proof"]
    assert "E7_CONFIRMATION" in out["missing_proof"]
    assert out["available_space_atr"] == 1.5223
    assert "STRUCTURAL_SPACE_INSUFFICIENT" not in out["missing_proof"]
