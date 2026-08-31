from __future__ import annotations

from production_v2.e2_brain import _classify_opportunity, analyze_e2


def _bars(n: int = 100):
    bars = []
    price = 100.0
    for i in range(n):
        open_ = price
        close = price - 0.35 if i > 5 else price
        high = max(open_, close) + 0.08
        low = min(open_, close) - 0.08
        bars.append({"open": open_, "high": high, "low": low, "close": close})
        price = close
    return bars


def test_e2_emits_a_complete_professional_opportunity_thesis():
    result = analyze_e2({"bars": _bars(), "E1_result": {"directional_pressure": "BEARISH", "market_state": "TREND_DOWN"}})
    reasoning = result.get("professional_reasoning") or {}
    assert result["reasoning_mode"] == "SINGLE_PROFESSIONAL_CORE"
    assert result["sub_engines_active"] is False
    assert result["question"] == "What opportunity is the market offering right now?"
    assert reasoning.get("question") == result["question"]
    assert reasoning.get("conclusion") not in (None, "", "UNRESOLVED")
    for key in ("why_now", "expected_path", "required_evidence", "invalidation_conditions", "timing", "opportunity_quality"):
        assert reasoning.get(key) not in (None, "", [], {})
    assert result.get("direction") in {"UP", "DOWN", "NEUTRAL"}
    assert result.get("regime") in {"TREND", "BREAKOUT", "MEAN_REVERSION", "RANGE", "TRANSITION"}


def test_e2_does_not_delegate_thesis_to_e1():
    bars = _bars()
    own = analyze_e2({"bars": bars, "E1_result": {"directional_pressure": "BULLISH", "market_state": "TREND_UP"}})
    no_e1 = analyze_e2({"bars": bars})
    assert own["regime"] == no_e1["regime"]
    assert own["direction"] == no_e1["direction"]
    assert own["independence"] == "E2_FIRST_E1_CROSS_CHECK"


def test_e2_counter_evidence_changes_thesis_quality_not_direction_by_command():
    bars = _bars()
    # Create a strong opposing auction at the latest candle without supplying a trade command.
    bars[-1]["open"] = bars[-1]["close"] + 1.0
    bars[-1]["high"] = bars[-1]["open"] + 0.05
    bars[-1]["low"] = bars[-1]["close"] - 0.05
    result = analyze_e2({"bars": bars, "E1_result": {"directional_pressure": "BEARISH"}})
    assert result["decision"] is None
    assert result["gate"] is None
    assert isinstance(result["counter_evidence"], list)
    assert isinstance(result["invalidation_evidence"], list)
    assert result["professional_reasoning"]["counter_evidence_count"] == len(result["counter_evidence"])


def test_e2_timing_distinguishes_idea_from_entry():
    result = analyze_e2({"bars": _bars(), "E1_result": {"directional_pressure": "BEARISH"}})
    assert result["timing_state"] in {"EARLY", "DEVELOPING", "READY_FOR_CONFIRMATION", "LATE", "MISSED", "WAIT"}
    assert result["decision"] is None
    assert result["trigger"] is None
    assert result["entry"] is None


def test_e2_insufficient_data_is_an_explicit_no_thesis_state():
    result = analyze_e2({"bars": _bars(20)})
    assert result["state"] == "UNAVAILABLE"
    assert result["opportunity"] == "NONE"
    assert result["decision"] is None
    assert result["gate"] is None


def test_e2_acceptance_does_not_override_location_and_space_vetoes():
    result = _classify_opportunity(
        up=7, down=0, auction="BUY_SIDE_ACCEPTANCE", balanced=False,
        acceptance=True, rejection=False, space_atr=0.35, location_ok=False,
    )
    assert result["direction"] == "BUY"
    assert result["opportunity_maturity"] == "DEVELOPING"
    assert "LOCATION_NOT_ADVANTAGEOUS" in result["blockers"]
    assert "INSUFFICIENT_OPPOSING_SPACE" in result["blockers"]


def test_e2_conflicting_directional_evidence_is_explicit_and_not_confirmed():
    result = _classify_opportunity(
        up=5, down=4, auction="BUY_SIDE_ACCEPTANCE", balanced=False,
        acceptance=True, rejection=False, space_atr=2.0, location_ok=True,
    )
    assert result["direction"] == "BUY"
    assert result["opportunity_maturity"] == "DEVELOPING"
    assert "DIRECTIONAL_EVIDENCE_CONFLICT" in result["blockers"]


def test_e2_exposes_regime_phase_playbooks_and_reasoning_trace():
    result = analyze_e2({"bars": _bars()})
    assert result["regime_phase"] in {"EARLY", "MATURE", "LATE", "FAILED", "UNRESOLVED"}
    assert isinstance(result["candidate_playbooks"], list)
    assert result["preferred_playbook"] is None or isinstance(result["preferred_playbook"], dict)
    assert isinstance(result["opportunity_bias"], str)
    assert isinstance(result["evidence"], list)
    assert isinstance(result["conflicts"], list)
    assert isinstance(result["reasoning_trace"], list)
