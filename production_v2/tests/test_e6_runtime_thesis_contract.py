from production_v2.contracts import EngineResult
import production_v2.e6_runtime_authority as runtime


def test_runtime_membrane_never_promotes_legacy_no_setup_into_trade_setup(monkeypatch):
    legacy = EngineResult(
        "E6", "Setup Brain", False, 0.0,
        {
            "state": "NO_SETUP", "setup": "NO_SETUP", "direction": "NEUTRAL",
            "trade_ready": False, "gate_passed": False,
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
    result = runtime._runtime_watch_or_original(legacy, {})
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert result.output["watch_only"] is True
    assert result.output["trade_ready"] is False
    assert result.output["gate_passed"] is False
