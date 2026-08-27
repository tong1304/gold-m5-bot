"""Professional E1 classification matrix.

E1 is a market-state analyst only. These tests validate state classification,
conflict handling, transition protection, data integrity, and ownership.
"""
from __future__ import annotations

import math
import pytest

from production_v2.e1_brain import analyze_e1


def _bars(closes, spread=0.10):
    bars = []
    prev = closes[0]
    for i, close in enumerate(closes):
        open_ = prev if i else close
        bars.append({
            "open": open_,
            "high": max(open_, close) + spread,
            "low": min(open_, close) - spread,
            "close": close,
        })
        prev = close
    return bars


def _trend(direction=1, n=140):
    closes = [100.0 + direction * (0.28 * i + 0.18 * math.sin(i * math.pi / 2)) for i in range(n)]
    return _bars(closes)


def _range(n=140):
    return _bars([100.0 + 0.75 * math.sin(i * math.pi / 4) for i in range(n)], spread=0.08)


def _compression(n=140):
    return _bars([100.0 + 0.06 * math.sin(i * math.pi / 4) for i in range(n)], spread=0.015)


def _transition_up_to_down():
    closes = [100.0 + 0.30 * i + 0.12 * math.sin(i * math.pi / 2) for i in range(95)]
    last = closes[-1]
    closes.extend(last - 0.65 * (j + 1) + 0.08 * math.sin(j * math.pi / 2) for j in range(25))
    return _bars(closes)


MATRIX = [
    ("established_up", _trend(1), "TREND_UP"),
    ("established_down", _trend(-1), "TREND_DOWN"),
    ("balanced_range", _range(), "RANGE"),
    ("volatility_compression", _compression(), "COMPRESSION"),
    ("regime_handoff", _transition_up_to_down(), "TRANSITION"),
]


@pytest.mark.parametrize("name,bars,expected", MATRIX, ids=[x[0] for x in MATRIX])
def test_professional_market_state_matrix(name, bars, expected):
    result = analyze_e1(bars)
    assert result["analysis_status"] == "COMPLETE", name
    assert result["market_state"] == expected, result
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"


def test_insufficient_data_is_withheld():
    result = analyze_e1(_trend(1, n=40))
    assert result["market_state"] == "UNCLEAR"
    assert result["analysis_status"] == "INCOMPLETE"
    assert result["trend_state"] == "NONE"


def test_invalid_ohlc_is_not_silently_accepted():
    bars = _trend(1)
    bars[10]["high"] = bars[10]["low"] - 1.0
    result = analyze_e1(bars)
    assert result["conflicts"]
    assert result["trade_decision_authority"] is False


def test_transition_has_explicit_conflict_reason():
    result = analyze_e1(_transition_up_to_down())
    assert result["market_state"] == "TRANSITION"
    assert result["transition"] == "PRESENT"
    assert result["trend_state"] == "NONE"
    assert result["reasons"]
    assert result["professional_reasoning"]["trend_confirmed"] is False


def test_e1_ownership_excludes_downstream_decisions():
    result = analyze_e1(_trend(1))
    ownership = result["professional_reasoning"]["ownership_boundaries"]
    assert "market_regime" in ownership["owns"]
    for item in (
        "opportunity_setup", "liquidity_auction", "trade_location",
        "entry_confirmation", "trade_economics", "risk_management",
        "trade_execution",
    ):
        assert item in ownership["does_not_own"]


def test_professional_reasoning_trace_explains_classification():
    result = analyze_e1(_trend(1))
    trace = " | ".join(result["reasoning_trace"])
    for marker in (
        "QUESTION -> What is the market doing right now?",
        "PRESSURE ->", "PERSISTENCE ->", "REGIME_CONFIRMATION ->", "STATE ->",
    ):
        assert marker in trace
