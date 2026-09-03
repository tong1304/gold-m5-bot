from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, output.get("gate_passed"), 0.0, output, ())


def _btc_upstream(e2):
    return {
        "E1": _engine("E1", {
            "directional_pressure": "BALANCED",
            "market_state": "TRANSITION",
            "trend_state": "NONE",
        }),
        "E2": _engine("E2", e2),
        "E3": _engine("E3", {
            "external_state": "UP",
            "internal_state": "UP",
            "structure_integrity": "VALID",
            "structure_completeness": "COMPLETE",
        }),
        "E4": _engine("E4", {
            "event": "HIGH_LIQUIDITY_INTERACTION",
            "liquidity_taker": "BUYERS",
            "auction_state": "PENDING",
        }),
        "E5": _engine("E5", {
            "finding": "FAVORABLE_LOCATION",
            "value_state": "BELOW_VALUE",
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_long": 2.174,
        }),
    }


def test_e6_tracks_btc_causal_opportunity_before_trigger_proof():
    result = analyze_e6({"symbol": "BTC/USD", "timeframe": "M5"}, _btc_upstream({
        "finding": "UP opportunity is developing",
        "opportunity_state": "DEVELOPING",
        "counter_evidence": ["AUCTION_CONFIRMATION_PENDING", "LOCATION_NOT_ADVANTAGEOUS"],
    }))
    out = result.output

    assert out["direction"] == "BUY"
    assert out["setup_family"] == "LIQUIDITY_RESPONSE"
    assert out["opportunity_stage"] == "FORMING"
    assert out["state"] == "FORMING"
    assert out["trade_ready"] is False
    assert out["gate_passed"] is False
    assert "NO_CAUSAL_OPPORTUNITY" not in out["reason_codes"]
    assert "E4_AUCTION_FOLLOW_THROUGH" in out["missing_proof"]
    assert "E7_CONFIRMATION" in out["missing_proof"]


def test_e6_does_not_erase_thesis_when_e2_becomes_confirmed():
    result = analyze_e6({"symbol": "BTC/USD", "timeframe": "M5"}, _btc_upstream({
        "finding": "UP opportunity is confirmed",
        "opportunity_state": "CONFIRMED",
        "opportunity_direction": "UP",
    }))
    out = result.output

    assert out["direction"] == "BUY"
    assert out["setup_family"] == "LIQUIDITY_RESPONSE"
    assert out["state"] != "NO_SETUP"
    assert "NO_CAUSAL_OPPORTUNITY" not in out["reason_codes"]
