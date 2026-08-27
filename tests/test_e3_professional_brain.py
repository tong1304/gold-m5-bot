from production_v2.e3_brain import _bos, _sweep_failure, analyze_e3
from production_v2.engines import run_engine


def _bar(close, open_=100.0, high=None, low=None):
    high = max(open_, close) if high is None else high
    low = min(open_, close) if low is None else low
    return {"open": open_, "high": high, "low": low, "close": close}


def _bars(values):
    bars = []
    for i, close in enumerate(values):
        prev = values[i - 1] if i else close
        bars.append({"open": prev, "high": max(prev, close) + 0.4, "low": min(prev, close) - 0.4, "close": close})
    return bars


def test_e3_always_returns_structural_answer_with_professional_contract():
    result = analyze_e3(_bars([100 + i * 0.8 for i in range(60)]))
    assert result["analysis_status"] == "COMPLETE"
    assert result["question"] == "What is price structure communicating?"
    assert result["finding"] != "UNRESOLVED"
    assert result["structure_state"] == "DIRECTIONAL_CONTEXT_UNCONFIRMED"
    assert "NO_CONFIRMED_EXTERNAL_BOS" in result["reason_codes"]
    assert result["trade_decision_authority"] is False
    assert result["gate"] is None
    assert result["upstream_direction_used"] is False


def test_e3_does_not_consume_upstream_direction_or_decision():
    snapshot = {"bars": _bars([100 + i * 0.5 for i in range(60)]), "E1_result": {"direction": "DOWN", "decision": "SELL"}, "E2_result": {"direction": "DOWN"}}
    result = run_engine("E3", snapshot, {"E1": snapshot["E1_result"], "E2": snapshot["E2_result"]})
    assert result.output["upstream_direction_used"] is False
    assert result.output["upstream_decisions_used"] is False
    assert result.output["decision"] is None
    assert result.output["gate"] is None
    assert result.output["finding"] != "UNRESOLVED"


def test_bos_confirms_close_beyond_structural_level():
    result = _bos([_bar(111.0, open_=108.0)], [{"index": 10, "price": 110.0, "label": "HH"}], [{"index": 11, "price": 90.0, "label": "HL"}], atr=2.0, prior_structure="UP")
    assert result["confirmed"] is True
    assert result["direction"] == "UP"
    assert result["event"] == "CONFIRMED_BOS"
    assert result["level"] == 110.0


def test_wick_through_level_without_close_is_not_bos():
    result = _bos([_bar(109.0, open_=108.0, high=112.0, low=107.5)], [{"index": 10, "price": 110.0, "label": "HH"}], [{"index": 8, "price": 100.0, "label": "HL"}], atr=2.0, prior_structure="UP")
    assert result["confirmed"] is False
    assert result["event"] == "NO_BOS"


def test_failed_break_detects_sweep_and_close_back_inside_level():
    result = _sweep_failure([_bar(109.0, open_=108.0, high=112.0, low=107.5)], [{"index": 10, "price": 110.0, "label": "HH"}], [{"index": 8, "price": 100.0, "label": "HL"}])
    assert result["confirmed"] is True
    assert result["event"] == "FAILED_BOS"
    assert result["direction"] == "DOWN"


def test_choch_is_used_when_breaking_against_established_structure():
    result = _bos([_bar(111.0, open_=108.0)], [{"index": 10, "price": 110.0, "label": "HH"}], [{"index": 11, "price": 90.0, "label": "LL"}], atr=2.0, prior_structure="DOWN")
    assert result["confirmed"] is True
    assert result["direction"] == "UP"
    assert result["event"] == "CONFIRMED_CHOCH"


def test_bos_requires_meaningful_close_distance():
    result = _bos([_bar(110.05, open_=109.0, high=110.2, low=108.8)], [{"index": 10, "price": 110.0, "label": "HH"}], [{"index": 8, "price": 100.0, "label": "HL"}], atr=2.0, prior_structure="UP")
    assert result["confirmed"] is False
    assert result["event"] == "NO_BOS"


def test_failed_break_requires_meaningful_close_back_inside_level():
    result = _sweep_failure([_bar(109.95, open_=110.10, high=110.30, low=109.70)], [{"index": 10, "price": 110.0, "label": "HH"}], [{"index": 8, "price": 100.0, "label": "HL"}], atr=2.0)
    assert result["confirmed"] is False
    assert result["event"] == "NO_FAILURE"


def test_e3_preserves_internal_external_divergence_and_never_becomes_a_gate():
    result = analyze_e3(_bars([100 + i * 0.4 for i in range(90)] + [135, 134, 133, 132, 131, 130]))
    assert result["trade_decision_authority"] is False
    assert result["gate"] is None
    assert result["upstream_decisions_used"] is False
    assert result["score_used"] is False
    assert isinstance(result["conflicts"], list)
