from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_V2 = ROOT / "production_v2"


def test_runtime_does_not_monkey_patch_pipeline_run():
    app_source = (PRODUCTION_V2 / "app.py").read_text(encoding="utf-8")
    assert "ProductionPipeline.run =" not in app_source
    assert "_run_with_lifecycle" not in app_source


def test_canonical_brain_modules_exist():
    for engine in range(1, 10):
        assert (PRODUCTION_V2 / f"e{engine}_brain.py").is_file()


def test_execution_state_is_explicit_and_separate_from_e9_authorization():
    contracts = (PRODUCTION_V2 / "contracts.py").read_text(encoding="utf-8")
    execution = (PRODUCTION_V2 / "execution_state.py").read_text(encoding="utf-8")
    assert "execution_state" in contracts
    assert "ORDER_INTENT" in execution
    assert "POSITION_OPEN" in execution
    assert "authorize_order" in execution


def test_opportunity_namespace_has_explicit_lifecycle_and_memory_modules():
    assert (PRODUCTION_V2 / "opportunity" / "lifecycle.py").is_file()
    assert (PRODUCTION_V2 / "opportunity" / "memory.py").is_file()


def test_e9_has_one_canonical_authority_boundary():
    authority = (PRODUCTION_V2 / "governance" / "final_authority.py").read_text(encoding="utf-8")
    assert "enforce_final_authority" in authority
    assert "decision_authority" not in authority or "E9" in authority
