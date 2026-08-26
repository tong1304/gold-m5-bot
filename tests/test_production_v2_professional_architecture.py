from production_v2.contracts import EngineResult
from production_v2 import professional_brain as brain


def _raw(engine_id, score=70.0, reasons=(), reasoning=None, plan=None):
    output = {
        "professional_reasoning": reasoning or {},
        "evidence_quality": score,
        "professional_reason_codes": list(reasons),
    }
    if plan is not None:
        output["trade_plan"] = plan
    return EngineResult(engine_id, engine_id, bool(not reasons), score, output, tuple(reasons))


def test_specialist_does_not_turn_weak_confirmation_into_pipeline_failure(monkeypatch):
    monkeypatch.setattr(
        brain,
        "_legacy_run_engine",
        lambda engine_id, context: _raw(
            engine_id,
            score=65,
            reasoning={"confirmation": "CONFIRMATION_WAIT"} if engine_id == "E7" else {},
            reasons=("E7_CONFIRMATION_INSUFFICIENT",) if engine_id == "E7" else (),
        ),
    )
    result = brain.run_professional_engine("E7", {})
    assert result.gate_passed is True
    assert result.output["analysis_complete"] is True
    assert result.output["trade_decision_authority"] is False
    assert result.output["analysis_status"] == "NOT_CONFIRMED"


def test_only_e9_can_emit_trade_decision():
    upstream = [
        _raw("E1", 85), _raw("E2", 80), _raw("E3", 85), _raw("E4", 75),
        _raw("E5", 80), _raw("E6", 82),
        _raw("E7", 90, reasoning={
            "confirmation": "CONFIRMATION_PASS",
            "trigger_quality": "QUALITY_PASS",
            "follow_through": "FOLLOW_THROUGH_OBSERVED",
        }),
        _raw("E8", 90, plan={
            "valid": True, "direction": "SELL", "rr_tp2": 2.0, "min_rr": 1.5,
        }),
    ]
    e9 = brain.run_professional_e9({}, upstream)
    assert e9.output["decision_authority"] == "E9"
    assert e9.output["trade_decision_authority"] is True
    assert e9.output["decision"] in {"BUY", "SELL", "NO_TRADE"}
    assert all(e.output.get("trade_decision_authority") is not True for e in upstream)


def test_no_trade_keeps_evidence_score_instead_of_zeroing_it():
    upstream = [_raw(f"E{i}", 80) for i in range(1, 9)]
    e9 = brain.run_professional_e9({}, upstream)
    assert e9.output["decision"] == "NO_TRADE"
    assert e9.output["evidence_score"] > 0
    assert e9.output["edge_score"] == e9.output["evidence_score"]
