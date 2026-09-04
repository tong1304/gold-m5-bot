import production_v2
from production_v2 import e6_brain


def test_package_runtime_keeps_e6_analyze_in_e6_brain():
    assert e6_brain.analyze_e6.__module__ == "production_v2.e6_brain"
    assert e6_brain.analyze_e6.__name__ == "analyze_e6"
    assert not hasattr(e6_brain, "_E6_PENDING_COUNTERFLOW_RUNTIME_INSTALLED")
    assert not hasattr(e6_brain, "_E6_OPPORTUNITY_GUARD_INSTALLED")
    assert not hasattr(e6_brain, "_E6_RUNTIME_AUTHORITY_INSTALLED")
