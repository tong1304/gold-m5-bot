import ast
from pathlib import Path

from production_v2.pipeline import ProductionPipeline


LEGACY_NAMES = {
    "v11", "v12", "engine_v11", "scheduler_v11", "live_scanner_v11",
    "engine_v42", "engine_v5", "engine_v6", "engine_v7", "engine_v9_1", "engine_v9_2",
}


def sample_data():
    bars = []
    for i in range(30):
        base = 100.0 + i * 0.5
        bars.append({"open": base, "high": base + 1, "low": base - 1, "close": base + 0.5})
    return {"symbol": "TEST", "timeframe": "M5", "bars": bars}


def test_pipeline_is_exactly_e1_to_e9():
    result = ProductionPipeline().run(sample_data())
    assert [e.engine_id for e in result.engines] == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"]
    assert result.engines[-1].engine_id == "E9"
    assert result.as_dict()["decision_authority"] == "E9"
    assert result.legacy_runtime is False


def test_production_v2_source_has_no_legacy_imports():
    root = Path("production_v2")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
                assert not set(names) & LEGACY_NAMES, path
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in LEGACY_NAMES, path


def test_health_contract():
    from production_v2.app import app
    response = app.test_client().get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["system"] == "9-ENGINE"
    assert body["version"] == "production-v2"
    assert body["legacy_runtime"] is False
    assert body["decision_authority"] == "E9"
