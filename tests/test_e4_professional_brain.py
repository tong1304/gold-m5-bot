from production_v2.e4_brain import analyze_e4
from production_v2.engines import run_engine


def _bars(values):
    return [{"open": v - 0.2, "high": v + 0.5, "low": v - 0.5, "close": v} for v in values]


def test_e4_is_standalone_and_pauses_legacy_specialists():
    bars = _bars([100 + i * 0.1 for i in range(30)])
    result = run_engine("E4", {"bars": bars}, {"E1": {"engine_id": "E1", "evidence": {"output": {"score": 99, "gate": True, "direction": "UP"}}}})
    assert result.engine_id == "E4"
    assert result.gate_passed is None
    assert result.output["architecture"] == "E4_SINGLE_PROFESSIONAL_BRAIN_V10"
    assert result.output["specialists_active"] is False
    assert result.output["specialists_status"] == "PAUSED"
    assert result.output["decision"] is None
    assert result.output["decision_authority"] == "E9_ONLY"
    assert result.output["evidence"]["decisions_used"] is False
    assert result.output["evidence"]["gates_used"] is False
    assert result.output["evidence"]["scores_used"] is False


def test_e4_detects_closed_candle_high_sweep_rejection():
    bars = _bars([100 + i * 0.05 for i in range(35)])
    bars.extend([
        {"open": 101.0, "high": 102.0, "low": 100.8, "close": 101.8},
        {"open": 101.7, "high": 103.0, "low": 101.0, "close": 101.2},
    ])
    result = analyze_e4(bars)
    assert result["analysis_status"] == "COMPLETE"
    assert result["event"]["type"] == "HIGH_SWEEP_REJECTION"
    assert result["event"]["liquidity_state"] == "TAKEN"
    assert result["directional_implication"] == "DOWN"
    assert result["evidence"]["raw_market_data_used"] is True


def test_e4_does_not_turn_context_direction_into_a_trade_decision():
    bars = _bars([100 + i * 0.05 for i in range(35)])
    evidence = {"E1": {"evidence": {"output": {"direction": "BUY", "score": 100, "gate": True}}}}
    result = analyze_e4(bars, evidence)
    assert result["contextual_direction_hint"] == "UP"
    assert result.get("decision") is None
    assert result["evidence"]["scores_used"] is False
    assert result["evidence"]["gates_used"] is False


def test_e4_emits_freshness_and_auction_evidence():
    bars = _bars([100 + i * 0.05 for i in range(60)])
    result = analyze_e4(bars)
    liquidity = result["liquidity_map"]
    assert "fresh_high_zones" in liquidity
    assert "fresh_low_zones" in liquidity
    assert "consumed_high_zones" in liquidity
    assert "consumed_low_zones" in liquidity
    assert result["auction_state"] in {"REJECTION", "ACCEPTANCE", "BALANCED", "UNRESOLVED"}
    assert "missing_evidence" in result
    assert "conflicts" in result
