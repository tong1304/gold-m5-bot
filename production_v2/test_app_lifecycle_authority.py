import os

os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"

from production_v2 import app as app_module
from production_v2.pipeline import ProductionPipeline


def test_app_does_not_replace_pipeline_run_with_legacy_single_lifecycle_wrapper():
    assert ProductionPipeline.run.__module__ == "production_v2.pipeline"
    assert app_module.pipeline.run.__func__ is ProductionPipeline.run


def test_app_exposes_pipeline_lifecycle_unchanged():
    assert app_module.pipeline.__class__ is ProductionPipeline
    assert not hasattr(app_module, "_ORIGINAL_PIPELINE_RUN")
    assert not hasattr(app_module, "_current_opportunity_input")
