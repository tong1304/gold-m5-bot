from production_v2.contracts import EngineResult
from production_v2.opportunity_timing_runtime_hotfix import _apply, _merge_evidence
import production_v2.pipeline as pipeline_module


def _result(output):
    return EngineResult("E6", "Opportunity Thesis", False, 0.0, output, ())


def _early_result():
    return _apply(
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
                "observations": [
                    "event=HIGH_FAILED_BREAK_RECLAIM",
                    "event_level=4409.78",
                    "event_atr_frozen=7.85",
                    "event_age_bars=1",
                    "auction_quality=72.0",
                    "liquidity_quality=80.0",
                    "auction_state=PENDING",
                ],
            }),
            "E5": _result({
                "observations": [
                    "price=4412.28",
                    "available_space_atr_short=2.9",
                    "available_space_atr_long=1.6",
                ],
            }),
        },
    )


def test_merge_replaces_stale_zero_fields_with_e4_e5_evidence():
    merged = _merge_evidence(
        {
            "direction": "SELL",
            "auction_quality": 0.0,
            "available_space_atr": 0.0,
            "available_space_atr_short": 0.0,
        },
        {
            "observations": [
                "event=HIGH_FAILED_BREAK_RECLAIM",
                "event_level=4409.78",
                "event_atr_frozen=7.85",
                "event_age_bars=1",
                "auction_quality=72.0",
                "liquidity_quality=80.0",
                "auction_state=PENDING",
            ],
        },
        {
            "observations": [
                "price=4412.28",
                "available_space_atr_short=2.9",
                "available_space_atr_long=1.6",
            ],
        },
    )
    assert merged["auction_quality"] == "72.0"
    assert merged["event"] == "HIGH_FAILED_BREAK_RECLAIM"
    assert merged["available_space_atr_short"] == "2.9"
    assert merged["available_space_atr"] == "2.9"


def test_apply_marks_every_early_opportunity_for_e7_confirmation_without_trade_authority():
    out = _early_result().output
    timing = out["opportunity_timing"]
    assert timing["phase"] == "EARLY_OPPORTUNITY"
    assert out["candidate_type"] == "EARLY_OPPORTUNITY_CANDIDATE"
    assert out["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"
    assert out["execution_authority"] == "E9"
    assert out["trade_ready"] is False


def test_observation_backed_quality_and_space_are_not_lost():
    out = _early_result().output
    timing = out["opportunity_timing"]
    assert timing["evidence_quality"] == 72.0
    assert timing["available_space_atr"] == 2.9
    assert out["timing_membrane_version"] == "OPPORTUNITY_TIMING_MEMBRANE_V4"


def test_slow_early_opportunity_is_still_an_e7_confirmation_candidate():
    result = _early_result()
    assert result.output["opportunity_timing"]["phase"] == "EARLY_OPPORTUNITY"
    assert result.output["candidate_type"] == "EARLY_OPPORTUNITY_CANDIDATE"
    assert result.output["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"


def test_timing_hotfix_owns_final_e6_runtime_binding():
    binding = getattr(pipeline_module, "_E6_RUNTIME_OVERRIDE", None)
    assert binding is not None
    assert "opportunity_timing_runtime_hotfix" in getattr(binding, "__module__", "")
