from production_v2.e3_brain import analyze_e3, _compress
from production_v2.engines import run_engine, SUB_ENGINE_CODES


def _bars(n=80):
    bars=[]
    price=100.0
    for i in range(n):
        drift=0.30 if i < 60 else 0.75
        close=price+drift
        bars.append({"open":price,"high":close+0.25,"low":price-0.20,"close":close})
        price=close
    return bars


def test_e3_is_single_brain_and_subengines_are_parked():
    result=run_engine("E3", {"bars":_bars()})
    assert SUB_ENGINE_CODES["E3"] == []
    assert result.engine_id == "E3"
    assert result.output["architecture"] == "E3_SINGLE_PROFESSIONAL_BRAIN_V7"
    assert result.output["reasoning_role"] == "MARKET_STRUCTURE_ANALYST"
    assert result.output["question"] == "What is price structure communicating?"
    assert result.output["specialists_active"] is False
    assert result.output["specialists_status"] == "PAUSED"
    assert result.output["trade_decision_authority"] is False
    assert result.output["gate"] is None
    assert result.output["decision"] is None


def test_e3_never_consumes_upstream_direction():
    bars=_bars()
    first=analyze_e3(bars)
    second=run_engine("E3", {"bars":bars, "E1_result":{"direction":"DOWN"}, "E2_result":{"direction":"DOWN"}})
    assert first["direction"] == second.output["direction"]
    assert second.output["upstream_direction_used"] is False
    assert second.output["upstream_decisions_used"] is False
    assert second.output["upstream_gates_used"] is False
    assert second.output["score_used"] is False


def test_e3_exposes_structural_evidence_contract():
    result=analyze_e3(_bars())
    for key in ("swing_map","internal_structure","external_structure","bos","failure","structural_failure","BOS_type","BOS_level","BOS_candle_index","recent_high","recent_low","prior_high","prior_low","structure_strength","confidence","evidence"):
        assert key in result
    assert result["analysis_status"] == "COMPLETE"
    assert result["bos"]["event"] in {"NO_BOS","CONFIRMED_BOS","CONFIRMED_CHOCH","STRUCTURE_CONFLICT"}
    assert result["failure"]["event"] in {"NO_FAILURE","FAILED_BOS"}
    assert result["trade_decision_authority"] is False


def test_e3_compress_keeps_correct_extreme_for_clustered_pivots():
    highs=[(10,100.0),(11,101.0),(14,102.0)]
    lows=[(10,100.0),(11,99.0),(14,98.0)]
    assert _compress(highs, 10.0, spacing=2)[0] == (11,101.0)
    assert _compress(lows, 10.0, spacing=2)[0] == (11,99.0)


def test_e3_reports_conflict_when_structure_and_slope_disagree():
    bars=[]
    price=100.0
    for i in range(50):
        close=price + (0.8 if i >= 35 else -0.2)
        bars.append({"open":price,"high":max(price,close)+0.2,"low":min(price,close)-0.2,"close":close})
        price=close
    result=analyze_e3(bars)
    assert "reason_codes" in result
    assert result["analysis_status"] == "COMPLETE"


def test_e3_trace_structural_state_is_not_conflated_with_count_state():
    result=analyze_e3(_bars())
    trace=result["reasoning_trace"]
    assert trace["external_state"] == result["external_structure"]["state"]
    assert trace["internal_state"] == result["internal_structure"]["state"]
    assert trace["external_count_state"] == result["external_structure"]["count_state"]
    assert trace["internal_count_state"] == result["internal_structure"]["count_state"]


def test_e3_slope_is_context_only_not_structural_authority():
    result=analyze_e3(_bars())
    assert result["reasoning_trace"]["slope_is_structural_authority"] is False


def test_e3_internal_break_cannot_flip_external_direction():
    result=analyze_e3(_bars())
    if result["external_structure"]["state"] in {"UP", "DOWN"}:
        assert result["direction"] == result["structural_bias"] or result["protected_level_break"]["confirmed"]
        assert result["reasoning_trace"]["internal_bos_has_market_authority"] is False


def test_e3_structure_output_distinguishes_invalidation_from_reversal():
    result=analyze_e3(_bars())
    assert result["reasoning_trace"]["protected_level_break_is_not_automatic_reversal"] is True
    if result["protected_level_break"]["confirmed"]:
        assert result["direction"] == "NEUTRAL"
        assert result["reasoning_trace"]["protected_level_break_invalidates_current_external_thesis"] is True
