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


def test_nine_brain_governance_module_is_present():
    governance = ROOT / "professional_governance.py"
    assert governance.exists()
    tree = ast.parse(governance.read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert {"audit_engines", "enforce_final_authority"}.issubset(names)


def test_pending_engine_gates_are_not_mislabeled_as_hard_conflicts():
    from professional_governance import audit_engines, enforce_final_authority

    results = {
        "E1": {"direction": "UP", "state": "TREND_UP"},
        "E2": {"state": "UNRESOLVED", "gate_passed": False},
        "E3": {"direction": "UP", "lifecycle": "CONFIRMED"},
        "E4": {"auction_state": "PENDING", "gate_passed": False},
        "E5": {"state": "FAVORABLE_LOCATION"},
        "E6": {"direction": "BUY", "maturity": "VALIDATING", "gate_passed": False},
        "E7": {"confirmation_state": "PENDING", "gate_passed": False},
        "E8": {"risk_state": "BLOCKED", "gate_passed": False},
        "E9": {"decision": "BUY", "all_gates_pass": False},
    }

    audit = audit_engines(results)

    assert audit["hard_veto"] is False
    assert "ENTRY_CONFIRMATION_NOT_PROVEN" not in audit["hard_vetoes"]
    assert "AUCTION_CONFIRMATION_PENDING" not in audit["hard_vetoes"]
    assert set(audit["pending_gates"]) >= {"E2", "E4", "E6", "E7", "E8"}

    decision, approved, reasons = enforce_final_authority(results["E9"], audit)
    assert decision == "NO_TRADE"
    assert approved is False
    assert "E9_ALL_GATES_NOT_PASSED" in reasons
