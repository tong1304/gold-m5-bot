from production_v2.pipeline import finalize_e6_output


def test_final_e6_membrane_cannot_expose_legacy_no_setup_for_watch():
    output = {
        "setup": "OPPORTUNITY_WATCH",
        "watch_only": True,
        "trade_ready": False,
        "direction": "SELL",
        "opportunity_stage": "CONTESTED",
        "finding": "No causal setup hypothesis survives current closed-candle evidence.",
    }

    normalized = finalize_e6_output(output)

    assert normalized["finding"] == "SELL opportunity is contested; causal setup is not yet proven."
    assert normalized["next_required_event"] == "NEXT_CLOSED_M5_CANDLE"
    assert normalized["watch_only"] is True
    assert normalized["trade_ready"] is False
