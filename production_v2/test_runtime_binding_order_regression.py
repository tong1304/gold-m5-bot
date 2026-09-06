import os

os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"

from production_v2 import e6_brain, e8_brain, e9_brain
from production_v2 import pipeline as pipeline_module


def test_package_final_runtime_bindings_keep_authoritative_brains_as_final_authority():
    # E6 may expose a policy-preserving runtime membrane, but the raw brain
    # remains the canonical authority captured by final_runtime_binding.
    assert pipeline_module._E6_FINAL_AUTHORITY is e6_brain.analyze_e6
    assert pipeline_module.analyze_e8 is e8_brain.analyze_e8
    assert pipeline_module.analyze_e9 is e9_brain.analyze_e9


def test_live_app_e6_surgery_survives_final_runtime_binding():
    from production_v2 import app as app_module
    from production_v2 import e6_pending_event_surgery

    assert pipeline_module.analyze_e6.__module__ == e6_pending_event_surgery.__name__
    assert pipeline_module.analyze_e6.__name__ == "patched_analyze_e6"
    assert getattr(pipeline_module, "_E6_RUNTIME_OVERRIDE").__module__ == e6_pending_event_surgery.__name__
    assert app_module.pipeline.__class__.__name__ == "ProductionPipeline"
