from __future__ import annotations

from production_v2.opportunity_layer import enrich_opportunity, recover_e9


def test_e1_opportunity_stays_in_market_state_boundary():
    out = enrich_opportunity(
        "E1",
        {"market_state": "TREND_UP", "direction": "BUY", "confidence": 0.8},
        {"symbol": "BTC", "timeframe": "M5"},
    )
    assert out["opportunity_direction"] == "BUY"
    assert "CONTINUATION" in out["opportunity"]["types"]
    assert out["opportunity_authority"] == "E1"
    assert "trade_plan" not in out


def test_e4_liquidity_event_becomes_opportunity_not_trade():
    out = enrich_opportunity(
        "E4",
        {"event": "HIGH_FAILED_BREAK_RECLAIM", "liquidity_quality": 0.8},
        {},
    )
    assert out["opportunity"]["types"] == ["LIQUIDITY_REVERSAL"]
    assert out["opportunity_authority"] == "E4"
    assert "decision" not in out


def test_e9_recovery_fails_closed_and_keeps_authority():
    out = recover_e9({
        "E1": type("R", (), {"output": {"direction": "BUY"}})(),
        "E3": type("R", (), {"output": {"direction": "BUY"}})(),
        "E6": type("R", (), {"output": {"direction": "BUY"}})(),
    })
    assert out["decision"] == "NO_TRADE"
    assert out["gate_passed"] is False
    assert out["market_control"]["authority"] == "E9"
