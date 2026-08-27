from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENGINE_IDS = range(1, 10)


def test_each_engine_has_exactly_one_brain_file_and_analyzer():
    for i in ENGINE_IDS:
        engine = f"e{i}"
        canonical = ROOT / f"{engine}_brain.py"
        assert canonical.exists(), f"missing canonical brain: {canonical.name}"

        variants = list(ROOT.glob(f"{engine}_brain_*.py"))
        assert not variants, f"duplicate/variant brain files: {[p.name for p in variants]}"

        tree = ast.parse(canonical.read_text(encoding="utf-8"))
        functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        analyzers = [n for n in functions if n.name == f"analyze_{engine}"]
        assert len(analyzers) == 1, f"{canonical.name} must expose exactly one analyze_{engine}()"


def test_no_legacy_e1_decision_layers_remain():
    forbidden = {
        "e1_reconciliation.py",
        "e1_transition_guard.py",
        "e1_transition_guard_v2.py",
        "e1_transition_guard_v3.py",
        "e1_brain_v3.py",
    }
    present = sorted(p.name for p in ROOT.iterdir() if p.is_file() and p.name in forbidden)
    assert not present, f"legacy E1 decision layers remain: {present}"
