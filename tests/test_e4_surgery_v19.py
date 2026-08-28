from production_v2.e4_brain import ARCHITECTURE, analyze_e4


def _rejection_bars():
    bars = [{"open": 100, "high": 101, "low": 99, "close": 100} for _ in range(40)]
    bars[30] = {"open": 104, "high": 105, "low": 103, "close": 104}
    for i in range(31, 36):
        bars[i] = {"open": 104, "high": 104.5, "low": 103.5, "close": 104}
    bars[36] = {"open": 104, "high": 105.7, "low": 103.9, "close": 104.5}
    bars[37] = {"open": 104.5, "high": 104.6, "low": 103.9, "close": 104.0}
    bars[38] = {"open": 104, "high": 104.2, "low": 103.8, "close": 103.8}
    bars[39] = {"open": 103.8, "high": 104.0, "low": 103.7, "close": 103.5}
    return bars


def _acceptance_bars():
    bars = [{"open": 100, "high": 101, "low": 99, "close": 100} for _ in range(40)]
    bars[30] = {"open": 104, "high": 105, "low": 103, "close": 104}
    for i in range(31, 37):
        bars[i] = {"open": 104, "high": 104.5, "low": 103.5, "close": 104}
    bars[37] = {"open": 104, "high": 105.8, "low": 103.9, "close": 105.4}
    bars[38] = {"open": 105.4, "high": 106.2, "low": 105.2, "close": 105.9}
    bars[39] = {"open": 105.9, "high": 106.4, "low": 105.6, "close": 106.1}
    return bars


def test_e4_is_single_analysis_only_liquidity_brain():
    result = analyze_e4(
        {"bars": _rejection_bars()},
        {"E1": {"decision": "BUY", "score": 100}, "E2": {"decision": "SELL"}, "E3": {"gate": True}},
    )
    assert result["architecture"] == ARCHITECTURE
    assert result["professional_brain"] is True
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["score"] is None
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["upstream_decisions_used"] is False
    assert result["upstream_gates_used"] is False
    assert result["scores_used"] is False
    assert result["evidence"]["decisions_used"] is False
    assert result["evidence"]["gates_used"] is False
    assert result["evidence"]["scores_used"] is False


def test_e4_sweep_rejection_requires_post_event_follow_through():
    result = analyze_e4({"bars": _rejection_bars()})
    assert result["event"]["type"] == "HIGH_SWEEP_REJECTION"
    assert result["event"]["liquidity_taker"] == "BUYERS"
    assert result["auction_state"] == "REJECTION_CONFIRMED"
    assert result["direction"] == "DOWN"
    assert result["direction_confirmed"] is True
    assert result["follow_through_bars"] >= 1
    assert "HIGH_SWEEP_REJECTION_CONFIRMED" in result["finding"]


def test_e4_acceptance_is_confirmed_only_after_follow_through():
    result = analyze_e4({"bars": _acceptance_bars()})
    assert result["event"]["type"] == "HIGH_ACCEPTANCE_CANDIDATE"
    assert result["auction_state"] == "ACCEPTANCE_CONFIRMED"
    assert result["direction"] == "UP"
    assert result["direction_confirmed"] is True
    assert result["follow_through_bars"] >= 1
    assert "HIGH_ACCEPTANCE_CANDIDATE_CONFIRMED" in result["finding"]


def test_e4_builds_liquidity_map_with_freshness_and_cluster_information():
    result = analyze_e4({"bars": _rejection_bars()})
    assert "high_zones" in result["liquidity_map"]
    assert "low_zones" in result["liquidity_map"]
    assert result["liquidity_map"]["high_zones"]
    assert all("freshness" in zone and "touches" in zone for zone in result["liquidity_map"]["high_zones"])


def test_e4_has_counter_evidence_and_invalidation_without_making_trade_decision():
    result = analyze_e4({"bars": _rejection_bars()})
    assert result["counter_evidence"]
    assert result["invalidation"]
    assert result["decision"] is None


def test_e4_insufficient_data_stays_neutral():
    result = analyze_e4({"bars": _rejection_bars()[:10]})
    assert result["analysis_status"] == "INCOMPLETE"
    assert result["direction"] == "NEUTRAL"
    assert result["auction_state"] == "UNRESOLVED"
    assert result["decision"] is None
