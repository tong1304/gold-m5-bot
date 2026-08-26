from __future__ import annotations

from production_v2.contracts import EngineResult
from production_v2 import pipeline as pipeline_module


def test_e1_to_e8_share_observations_without_sequential_decision_flow(monkeypatch):
    calls: list[tuple[str, tuple[str, ...], bool, bool]] = []

    def fake_run_engine(engine_id, snapshot, evidence_bus=None):
        evidence_bus = evidence_bus or {}
        calls.append(
            (
                engine_id,
                tuple(sorted(evidence_bus)),
                any(v.get("decision") is not None for v in evidence_bus.values() if isinstance(v, dict)),
                any(v.get("gate") is not None for v in evidence_bus.values() if isinstance(v, dict)),
            )
        )
        return EngineResult(
            engine_id,
            engine_id,
            None,
            80.0,
            {"specialists": {f"{engine_id}A": {"output": {"state": "OBSERVED"}}}},
            (),
        )

    def fake_e9(context, upstream, calibration=None):
        return EngineResult("E9", "Master Decision Brain", False, 0.0, {"decision": "NO_TRADE", "trade_plan": {}}, ())

    monkeypatch.setattr(pipeline_module, "run_engine", fake_run_engine)
    monkeypatch.setattr(pipeline_module, "run_professional_e9", fake_e9)

    result = pipeline_module.ProductionPipeline().run({"symbol": "GOLD", "timeframe": "M5", "bars": [{"close": 1.0}]})

    assert result.decision == "NO_TRADE"
    assert len(calls) == 16
    first_pass = calls[:8]
    second_pass = calls[8:]
    assert {x[0] for x in first_pass} == set(pipeline_module.ENGINE_ORDER)
    assert {x[0] for x in second_pass} == set(pipeline_module.ENGINE_ORDER)
    assert all(received == () for _, received, _, _ in first_pass)
    for engine_id, received, decisions, gates in second_pass:
        assert set(received) == set(pipeline_module.ENGINE_ORDER) - {engine_id}
        assert decisions is False
        assert gates is False


def test_specialist_gate_is_not_a_boolean_authority(monkeypatch):
    def fake_module(code):
        class Specialist:
            def run(self, context):
                return EngineResult(code, code, False, 80.0, {"state": "OBSERVED"}, ())

        return Specialist()

    from production_v2 import engines as engines_module
    monkeypatch.setattr(engines_module, "_module", fake_module)
    monkeypatch.setattr(engines_module, "SUB_ENGINE_CODES", {"E1": ["1A"]})
    monkeypatch.setattr(engines_module, "EVIDENCE_INPUTS", {"E1": ()})

    result = engines_module.run_engine("E1", {"bars": []}, {})

    assert result.gate_passed is None
    assert result.output["gate_semantics"] == "DISABLED_FOR_E1_E8"
    assert result.output["decision_authority"] == "E9_ONLY"
