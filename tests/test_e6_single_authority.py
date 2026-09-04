import importlib


def test_e6_is_not_wrapped_by_evidence_collaboration_runtime():
    e6 = importlib.import_module("production_v2.e6_brain")
    runtime = importlib.import_module("production_v2.evidence_collaboration_runtime")

    runtime.install(e6, importlib.import_module("production_v2.e9_brain"))

    assert e6.analyze_e6.__module__ == "production_v2.e6_brain"
    assert e6.analyze_e6.__name__ == "analyze_e6"
