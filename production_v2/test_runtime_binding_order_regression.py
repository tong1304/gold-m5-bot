import os

os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"

from production_v2 import e6_brain, e8_brain, e9_brain
from production_v2 import pipeline as pipeline_module


def test_final_runtime_bindings_use_guarded_analyzers():
    assert pipeline_module.analyze_e6 is e6_brain.analyze_e6
    assert pipeline_module.analyze_e8 is e8_brain.analyze_e8
    assert pipeline_module.analyze_e9 is e9_brain.analyze_e9
