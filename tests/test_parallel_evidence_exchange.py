from __future__ import annotations

import inspect

from production_v2 import pipeline as pipeline_module
from production_v2.nine_brain_surgery import harden_engine


def test_e1_to_e8_use_declared_evidence_dependencies_without_local_authority():
    expected = {
        "E1": (),
        "E2": ("E1",),
        "E3": (),
        "E4": ("E1", "E3"),
        "E5": ("E1", "E3", "E4"),
        "E6": ("E1", "E2", "E3", "E4", "E5"),
        "E7": ("E4", "E6"),
        "E8": ("E5", "E6", "E7"),
        "E9": ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"),
    }

    assert pipeline_module.ENGINE_ORDER == tuple(expected)
    assert pipeline_module.EVIDENCE_INPUTS == expected

    # The production architecture uses explicit specialist dependencies;
    # the obsolete generic run_engine/evidence-bus API must not be required.
    source = inspect.getsource(pipeline_module.ProductionPipeline.run)
    assert "run_engine(" not in source
    for engine_id in pipeline_module.ENGINE_ORDER:
        assert f"analyze_{engine_id[1:].lower()}(" in source


def test_specialist_gate_is_not_a_boolean_authority():
    for engine_id in pipeline_module.ENGINE_ORDER[:-1]:
        output = harden_engine(engine_id, {"state": "OBSERVED", "confidence": 0.8})
        contract = output["professional_contract"]
        assert contract["decision_authority"] == "E9_ONLY"
        assert contract["can_authorize_entry"] is False

    e8 = harden_engine("E8", {"risk_state": "READY", "confidence": 0.8})
    assert e8["execution_authorization"] == "NONE"

    e9 = harden_engine("E9", {"decision": "NO_TRADE"})
    assert e9["master_authority"] == "SOLE_FINAL_AUTHORITY"
    assert e9["upstream_evidence_only"] is True
