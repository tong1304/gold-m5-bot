import os


def test_production_runtime_installs_final_e6_authority():
    os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"
    import production_v2.app as app_module

    analyze = app_module.pipeline_module.analyze_e6
    assert analyze.__module__ == "production_v2.e6_runtime_authority"
    assert getattr(app_module.pipeline_module, "_E6_RUNTIME_AUTHORITY_INSTALLED", False) is True
