from __future__ import annotations

from e5_brain import ARCHITECTURE, analyze_e5


def _bars(n=80, start=100.0, step=0.10):
    bars = []
    price = start
    for i in range(n):
        close = price + step
        bars.append({"open": price, "high": close + 0.05, "low": price - 0.05, "close": close})
        price = close
    return bars


def test_e5_is_monolithic_and_has_no_specialists():
    result = analyze_e5({"bars": _bars()})
    assert result["architecture"] == ARCHITECTURE
    assert result["specialists_active"] is False
    assert result["specialists_status"] == "NOT_USED"
    assert result["decision_authority"] == "E9_ONLY"
    assert result["trade_decision_authority"] is False


def test_e5_uses_only_qualitative_upstream_context():
    bars = _bars()
    permitted = {
        "E1": {"evidence": {"output": {"market_state": "TREND_UP", "score": 99, "gate": True}}},
        "E2": {"evidence": {"output": {"regime": "TREND", "decision": "BUY"}}},
        "E3": {"evidence": {"output": {"classification": "BULLISH"}}},
        "E4": {"evidence": {"output": {"liquidity_location": "NEAR_BUY_SIDE_LIQUIDITY"}}},
    }
    result = analyze_e5({"bars": bars}, permitted)
    assert result["direction"] == "UP"
    assert result["professional_reasoning"]["upstream_decisions_used"] is False
    assert result["professional_reasoning"]["upstream_gates_used"] is False
    assert result["professional_reasoning"]["upstream_scores_used"] is False


def test_e5_detects_late_location_without_turning_into_trade_decision():
    bars = _bars(start=100.0, step=0.15)
    permitted = {"E1": {"evidence": {"output": {"market_state": "TREND_UP"}}}}
    result = analyze_e5({"bars": bars}, permitted)
    assert result["extension_state"] in {"STRETCHED", "EXTENDED", "EXCESSIVE", "NORMAL"}
    assert result["gate"] is None
    assert result["decision"] is None


def test_e5_with_insufficient_data_is_explicitly_incomplete():
    result = analyze_e5({"bars": _bars(20)})
    assert result["location_state"] == "UNRESOLVED"
    assert result["confidence"] == 0.0
    assert "E5_DATA_INCOMPLETE" in result["reason_codes"]
