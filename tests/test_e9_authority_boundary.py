from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_V2 = ROOT / "production_v2"


def test_pipeline_uses_canonical_e9_authority_boundary():
    source = (PRODUCTION_V2 / "pipeline.py").read_text(encoding="utf-8")
    assert "from .governance.final_authority import enforce_final_authority" in source
    assert "from .professional_governance import audit_engines" in source
    assert "from .professional_governance import audit_engines, enforce_final_authority" not in source
