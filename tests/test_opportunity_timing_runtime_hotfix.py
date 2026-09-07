from production_v2.contracts import EngineResult
from production_v2.opportunity_timing_runtime_hotfix import _apply, _merge_evidence


def _result(output):
    return EngineResult("E6", "Opportunity Thesis", False, 0.0, output, ())


def test_merge_replaces_stale_zero_fields_with_e4_e5_evidence():
    merged = _merge_evidence(
        {
            "direction": "SELL",
            "auction_quality": 0.0,
            "available_space_atr": 0.0,
            "available_space_atr_short": 0.0,
        },
        {
            "event": "HIGH_FAILED_BREAK_RECLAIM",
            "event_level": 4409.78,
            "event_atr_frozen": 7.85,
            "event_age_bars": 1,
            "auction_quality": 72.0,
            "liquidity_quality": 80.0,
            "auction_state": "PENDING",
        },
        {
            "price": 4412.28,
            "available_space_atr_short": 2.9,
            "available_space_atr_long": 1.6,
        },
    )
    assert merged["auction_quality"] == 72.0
    assert merged["event"] == "HIGH_FAILED_BREAK_RECLAIM"
    assert merged["available_space_atr_short"] == 2.9
    assert merged["available_space_atr"] == 2.9


def test_apply_marks_every_early_opportunity_for_e7_confirmation_without_trade_authority():
    result = _apply(
        _result({
            "direction": "SELL",
            "setup": "OPPORTUNITY_WATCH",
            "watch_only": True,
            "trade_ready": False,
            "auction_quality": 0.0,
            "available_space_atr": 0.0,
        }),
        {
            "E4": _result({
                "event": "HIGH_FAILED_BREAK_RECLAIM",
                "event_level": 4409.78,
                "event_atr_frozen": 7.85,
                "event_age_bars": 1,
                "auction_quality": 72.0,
                "liquidity_quality": 80.0,
                "auction_state": "PENDING",
            }),
            "E5": _result({
                "price": 4412.28,
                "available_space_atr_short": 2.9,
                "available_space_atr_long": 1.6,
            }),
        },
    )
    out = result.output
    timing = out["opportunity_timing"]
    assert timing["phase"] == "EARLY_OPPORTUNITY"
    assert out["candidate_type"] == "EARLY_OPPORTUNITY_CANDIDATE"
    assert out["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"
    assert out["execution_authority"] == "E9"
    assert out["trade_ready"] is False
