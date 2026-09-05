from production_v2 import pipeline as pipeline_module
from production_v2 import e6_brain
from production_v2.e6_pending_event_surgery import install


def test_pipeline_uses_runtime_patched_e6_analyzer():
    install(pipeline_module)
    assert pipeline_module.analyze_e6 is not e6_brain.analyze_e6
    assert pipeline_module.analyze_e6.__name__ == "patched_analyze_e6"
    assert pipeline_module.analyze_e6.__module__ == "production_v2.e6_pending_event_surgery"
