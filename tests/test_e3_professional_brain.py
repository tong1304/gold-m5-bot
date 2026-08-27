from production_v2.e3_brain import analyze_e3
from production_v2.engines import run_engine


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
    assert result["swing_map"]["highs"] or result["swing_map"]["lows"]
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


def test_e3_distinguishes_structure_failure_from_unconfirmed_break():
    values = [100, 101, 102, 101, 103, 104, 103, 105, 106, 105, 107, 108, 107, 109, 110, 109, 111, 112, 111, 113, 114, 113, 115, 116, 115, 117, 118, 117, 119, 120, 119, 121, 122, 121, 123, 124, 123, 125, 126, 125, 127, 128, 127, 129, 130, 129, 131, 132, 131, 133, 134, 133, 135, 136, 135, 137, 138, 137, 139, 140]
    result = analyze_e3(_bars(values))
    assert result["structure_state"] in {"CONTINUATION", "BREAKOUT_CONFIRMED"}
    assert result["bos"]["event"] in {"NO_BOS", "CONFIRMED_BOS"}
    assert "NO_CONFIRMED_BOS" in result["reason_codes"] or result["bos"]["confirmed"] is True
