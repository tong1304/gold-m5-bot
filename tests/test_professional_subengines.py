from trading_system.engines.e1.a_data_quality import SubEngine as E1A
from trading_system.engines.e3.b_structure_classification import SubEngine as E3B
from trading_system.engines.e4.b_sweep_detection import SubEngine as E4B
from trading_system.engines.e6.f_setup_maturity import SubEngine as E6F


def market_snapshot():
    bars = []
    price = 100.0
    for i in range(80):
        price += 0.35 if i < 55 else (-0.20 if i < 68 else 0.45)
        bars.append({
            "open": price - 0.20,
            "high": price + 0.45,
            "low": price - 0.45,
            "close": price,
            "volume": 100 + (i * 3),
        })
    return {"symbol": "XAU/USD", "timeframe": "M5", "bars": bars}


def test_subengines_emit_professional_evidence_contract():
    snapshot = market_snapshot()
    for cls in (E1A, E3B, E4B, E6F):
        result = cls().run(snapshot)
        assert result.output["evidence_type"]
        assert "observations" in result.output
        assert "analysis" in result.output
        assert "evidence" in result.output
        assert "counter_evidence" in result.output
        assert "confidence" in result.output
        assert "thesis" in result.output
        assert "missing_evidence" in result.output


def test_specialists_do_not_return_static_scores_for_identical_market_state():
    snapshot = market_snapshot()
    results = [E1A().run(snapshot), E3B().run(snapshot), E4B().run(snapshot), E6F().run(snapshot)]
    assert len({r.score for r in results}) >= 2
    assert len({r.output.get("evidence_type") for r in results}) == 4


def test_context_is_evidence_only():
    snapshot = market_snapshot()
    snapshot["E3_result"] = {
        "3B": {
            "decision": "BUY",
            "gate": True,
            "state": "BULLISH",
            "direction": "UP",
        }
    }
    result = E6F().run(snapshot)
    assert result.output.get("upstream_decisions_used") is False
    assert result.output.get("upstream_gates_used") is False
