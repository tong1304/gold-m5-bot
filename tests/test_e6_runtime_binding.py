from production_v2 import pipeline as pipeline_module
from production_v2 import e6_brain


def test_pipeline_uses_runtime_patched_e6_analyzer():
    assert pipeline_module.analyze_e6 is e6_brain.analyze_e6
