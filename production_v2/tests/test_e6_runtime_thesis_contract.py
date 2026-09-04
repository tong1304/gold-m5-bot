from production_v2.contracts import EngineResult
import production_v2.e6_runtime_authority as runtime


def test_runtime_rescue_preserves_causal_setup_thesis(monkeypatch):
    legacy = EngineResult(
        "E6", "Setup Brain", False, 0.0,
        {
            "state": "NO_SETUP",
            "setup": "NO_SETUP",
            "direction": "NEUTRAL",
            "trade_ready": False,
            "gate_passed": False,
            "finding": "No causal setup hypothesis survives current closed-candle evidence.",
            "reason_codes": ["NO_CAUSAL_OPPORTUNITY"],
            "reasons": ["NO_CAUSAL_OPPORTUNITY"],
        },
        ("NO_CAUSAL_OPPORTUNITY",),
    )
    candidate = {
        "direction": "BUY", "family": "LIQUIDITY_RESPONSE", "space": 1.20,
        "missing": ["E7_CONFIRMATION"], "support": ["E4_DIRECTIONAL_AUCTION_EVIDENCE"],
        "counter": [], "event_id": "candle-1",
    }
    monkeypatch.setattr(runtime, "_fallback_opportunity", lambda _upstream: candidate)

    original_watch = runtime._watch
    try:
        runtime._watch = lambda original, opportunity: EngineResult(
            "E6", "Setup Brain", False, 0.0,
            {"state": "SETUP_THESIS", "setup": opportunity["family"],
             "candidate_type": "SETUP_CANDIDATE", "direction": opportunity["direction"],
             "watch_only": False, "trade_ready": False, "gate_passed": False,
             "reason_codes": opportunity["missing"]},
            tuple(opportunity["missing"]),
        )
        result = runtime._runtime_watch_or_original(legacy, {})
    finally:
        runtime._watch = original_watch

    assert result.output["setup"] == "LIQUIDITY_RESPONSE"
    assert result.output["candidate_type"] == "SETUP_CANDIDATE"
    assert result.output["state"] == "SETUP_THESIS"
