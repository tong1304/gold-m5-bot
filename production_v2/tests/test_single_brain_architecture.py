import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_IDS = range(1, 10)


def _brain_source(engine_id: int) -> str:
    return (ROOT / f"e{engine_id}_brain.py").read_text(encoding="utf-8")


def test_each_engine_has_exactly_one_public_analyzer_and_no_cross_brain_imports():
    for engine_id in ENGINE_IDS:
        tree = ast.parse(_brain_source(engine_id))
        expected = f"analyze_e{engine_id}"
        analyzers = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("analyze_")
        ]
        assert analyzers == [expected]

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported = node.module or ""
                assert not any(
                    imported.endswith(f"e{other}_brain")
                    for other in ENGINE_IDS
                    if other != engine_id
                ), f"E{engine_id} imports another engine brain: {imported}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name.endswith(f"e{other}_brain")
                        for other in ENGINE_IDS
                        if other != engine_id
                    ), f"E{engine_id} imports another engine brain: {alias.name}"


def test_pipeline_is_the_only_orchestrator_and_does_not_use_brain_dispatcher():
    source = (ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert "from .engines import" not in source
    assert "run_engine(" not in source
    for engine_id in ENGINE_IDS:
        assert f"from .e{engine_id}_brain import analyze_e{engine_id}" in source
        assert f"analyze_e{engine_id}(" in source


def test_legacy_brain_dispatcher_is_removed():
    assert not (ROOT / "engines.py").exists()
