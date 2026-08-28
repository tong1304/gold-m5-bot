def test_e1_v16_runtime_synchronizes_stale_reasoning(monkeypatch):
    import production_v2.e1_professional_core_v16 as runtime

    fake = {
        "analysis_status": "COMPLETE",
        "market_state": "TREND_DOWN",
        "trend_state": "DOWN",
        "volatility_state": "CONTRACTING",
        "structure_state": "BEARISH",
        "directional_pressure": "DOWN",
        "transition": "WATCH",
        "transition_status": "WATCH",
        "dominant_direction": "DOWN",
        "professional_reasoning": {
            "market_state": "TREND_DOWN",
            "trend_state": "NONE",
        },
    }
    monkeypatch.setattr(runtime, "analyze_e1_professional_v15", lambda bars: dict(fake))
    out = runtime.analyze_e1_professional_v16([{}] * 60)
    assert out["trend_state"] == "DOWN"
    assert out["professional_reasoning"]["market_state"] == "TREND_DOWN"
    assert out["professional_reasoning"]["trend_state"] == "DOWN"
    assert out["professional_reasoning"]["reasoning_mirror_synchronized"] is True
