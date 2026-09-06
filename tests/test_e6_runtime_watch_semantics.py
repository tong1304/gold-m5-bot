from production_v2.e6_runtime_authority import _normalize_watch_semantics


def test_watch_finding_uses_opportunity_stage_and_direction():
    output = _normalize_watch_semantics(
        {
            "setup": "OPPORTUNITY_WATCH",
            "watch_only": True,
            "trade_ready": False,
            "direction": "SELL",
            "opportunity_stage": "CONTESTED",
            "finding": "No causal setup hypothesis survives current closed-candle evidence.",
        }
    )
    assert output["finding"] == "SELL opportunity is contested; causal setup is not yet proven."
    assert output["runtime_authority"] == "E6_FINAL_OPPORTUNITY_MEMBRANE_V8"
