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


def test_pipeline_stops_at_first_unresolved_engine_and_e9_remains_authority():
    result = ProductionPipeline().run(sample_data())
    ids = [e.engine_id for e in result.engines]
    assert ids[-1] == "E9"
    assert ids[:2] == ["E1", "E2"]
    assert result.engines[-2].engine_id in {"E2", "E3", "E4", "E5", "E6", "E7", "E8"}
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


def test_statistics_endpoints_are_production_v2_only():
    from production_v2.app import app
    client = app.test_client()
    for path in ("/api/statistics", "/statistics"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_json()
        assert body["system"] == "9-ENGINE"
        assert body["version"] == "production-v2"
        assert body["decision_authority"] == "E9"
        assert body["legacy_runtime"] is False
        assert body["engines"] == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"]
