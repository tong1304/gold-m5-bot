from __future__ import annotations

from production_v2.e1_professional_layer_v10 import analyze_e1_professional_v10


def _bars(closes):
    out = []
    for i, close in enumerate(closes):
        prev = closes[i - 1] if i else close
        out.append({"open": prev, "high": max(prev, close) + 0.25, "low": min(prev, close) - 0.25, "close": close})
    return out


def test_e1_exposes_explicit_professional_arbitration_contract():
    r = analyze_e1_professional_v10(_bars([5000.0 - i * 2.0 for i in range(120)]))
    assert r["e1_contract_version"] == "PROFESSIONAL_MARKET_STATE_V11"
    assert r["professional_reasoning"]["arbitration_order"] == [
        "DATA_QUALITY",
        "STRUCTURE",
        "LONG_HORIZON",
        "EMA_CONTEXT",
        "PRESSURE",
        "PERSISTENCE",
        "VOLATILITY",
        "COUNTER_EVIDENCE",
        "TRANSITION",
    ]
    assert r["professional_reasoning"]["trade_boundary"] == "MARKET_STATE_ONLY"


def test_e1_never_commits_transition_from_counter_pressure_alone():
    closes = [5000.0 - i * 2.0 for i in range(119)]
    closes.append(closes[-1] + 12.0)
    r = analyze_e1_professional_v10(_bars(closes))
    assert r["dominant_direction"] == "DOWN"
    assert r["market_state"] == "TREND_DOWN"
    assert r["transition_confirmed"] is False
    assert r["transition_committed"] is False
    assert "SINGLE_COUNTER_MOVE_CANNOT_COMMIT_TRANSITION" in r["reasons"]


def test_e1_transition_requires_structural_repricing_not_just_pressure_flip():
    closes = [5000.0 - i * 2.0 for i in range(100)]
    # A large counter move without persistent structural repricing must remain non-transition.
    closes.extend([4800.0, 4830.0, 4860.0, 4890.0])
    r = analyze_e1_professional_v10(_bars(closes))
    assert r["transition_confirmed"] is False
    assert r["transition_committed"] is False
    assert r["market_state"] != "TRANSITION"


def test_e1_output_isolated_from_other_engines():
    r = analyze_e1_professional_v10(_bars([5000.0 - i for i in range(120)]))
    assert r["e1_trade_authority"] is False
    assert r["trade_decision_authority"] is False
    assert "setup" not in r and "entry" not in r and "risk" not in r and "decision" not in r
