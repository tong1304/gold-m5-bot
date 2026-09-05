# Clean Architecture Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Production V2 structurally clean and single-owner without changing trading thresholds, E1–E9 authority, closed-candle/no-lookahead rules, or execution semantics.

**Architecture:** Keep `app.py` as HTTP/startup composition only; keep `pipeline.py` as the canonical E1→E9 orchestration; give lifecycle, persistence, economics, governance, and execution explicit ownership. Legacy surgery/version modules may remain temporarily during migration but must not be runtime authorities.

**Tech Stack:** Python 3, Flask, pytest, GitHub Actions, existing Production V2 modules.

**Spec:** `docs/superpowers/plans/2026-09-05-clean-architecture-pass.md`

## Global Constraints

- E9 remains the final decision authority.
- E9 authorization is never broker execution or `POSITION_OPEN`.
- M5 evaluation remains closed-candle-only and no-lookahead.
- Do not reduce E2/E5 thresholds or weaken any existing safety veto.
- Preserve existing public endpoints and response contracts unless a test proves a compatibility shim is required.
- Do not delete a legacy module until imports/usages/tests prove it is not a runtime dependency.

---

### Task 1: Establish architecture inventory and guardrails

**Files:**
- Create: `tests/test_production_v2_architecture.py`
- Modify: none initially

**Interfaces:**
- Consumes: current Production V2 import graph and runtime entrypoint.
- Produces: executable architecture guardrails identifying canonical runtime modules and forbidden monkey-patching/versioned-core imports.

- [ ] **Step 1: Write failing architecture tests**

```python
from pathlib import Path

ROOT = Path(__file__).parents[1] / "production_v2"


def test_app_does_not_monkey_patch_pipeline_run():
    text = (ROOT / "app.py").read_text()
    assert "ProductionPipeline.run =" not in text


def test_production_runtime_has_canonical_brain_modules():
    for engine in range(1, 10):
        assert (ROOT / f"e{engine}_brain.py").exists()


def test_versioned_e1_cores_are_not_runtime_imports():
    text = "\n".join(p.read_text(errors="ignore") for p in ROOT.glob("*.py"))
    for name in ("e1_professional_core_v10", "e1_professional_core_v11", "e1_professional_core_v12", "e1_professional_core_v13"):
        assert f"import {name}" not in text
        assert f"from .{name}" not in text
```

- [ ] **Step 2: Run the new tests and record current failures**

Run: `pytest -q tests/test_production_v2_architecture.py`
Expected: initial failure on the current monkey-patch/legacy dependency, proving the guardrail is meaningful.

- [ ] **Step 3: Keep the tests as permanent architectural contracts**

No implementation change is made in this task.

- [ ] **Step 4: Commit**

```bash
git add tests/test_production_v2_architecture.py
git commit -m "test: add production v2 architecture guardrails"
```

### Task 2: Make lifecycle ownership canonical

**Files:**
- Create: `production_v2/opportunity/lifecycle.py`
- Modify: `production_v2/opportunity_lifecycle.py`
- Modify: `production_v2/pipeline.py`
- Modify: `production_v2/app.py`
- Test: `tests/test_production_v2_architecture.py`
- Test: existing lifecycle/major-repair tests

**Interfaces:**
- Consumes: existing `advance_opportunity(previous, current)` behavior.
- Produces: one canonical lifecycle service API used by pipeline and app, with persistence injected at the boundary.

- [ ] **Step 1: Characterize existing lifecycle behavior with regression tests**

```python
from production_v2.opportunity_lifecycle import advance_opportunity


def test_authorization_never_means_execution():
    result = advance_opportunity(
        {},
        {"candidate": True, "direction": "SELL", "setup": "SETUP", "ready": True,
         "executed": False, "invalidated": False, "thesis_proven": True},
    )
    assert result["state"] in {"READY", "WAITING"}
    assert result["state"] != "EXECUTED"
```

- [ ] **Step 2: Run lifecycle regression tests**

Run: `pytest -q tests/test_production_v2_major_repair.py tests/test_production_v2_architecture.py`
Expected: the new architecture test fails only on ownership/monkey-patch conditions; existing lifecycle semantics remain green.

- [ ] **Step 3: Move the canonical function into `production_v2/opportunity/lifecycle.py`**

```python
from ..opportunity_lifecycle import advance_opportunity as _advance_opportunity


def advance_opportunity(previous, current):
    return _advance_opportunity(previous, current)
```

During migration, the old module becomes a compatibility facade rather than a second implementation.

- [ ] **Step 4: Inject lifecycle handling into `ProductionPipeline` instead of monkey-patching it from `app.py`**

The pipeline must expose one explicit lifecycle integration point and return the same `DecisionResult`; it must not infer broker execution from E9 approval.

- [ ] **Step 5: Remove `_run_with_lifecycle` and `ProductionPipeline.run = ...` from `app.py`**

`app.py` retains only composition/startup and endpoint handling.

- [ ] **Step 6: Run all lifecycle tests**

Run: `pytest -q tests/test_production_v2_major_repair.py tests/test_*lifecycle*.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add production_v2/opportunity/lifecycle.py production_v2/opportunity_lifecycle.py production_v2/pipeline.py production_v2/app.py tests
git commit -m "refactor: make opportunity lifecycle single-owner"
```

### Task 3: Separate persistence from lifecycle logic

**Files:**
- Create: `production_v2/opportunity/memory.py`
- Modify: `production_v2/opportunity_memory.py`
- Modify: `production_v2/app.py`
- Test: memory/lifecycle regression tests

**Interfaces:**
- Consumes: existing `load_all`, `save`, backend selection and PostgreSQL/file behavior.
- Produces: persistence adapter with no lifecycle decisions inside the storage implementation.

- [ ] **Step 1: Add adapter tests for file and database selection**

```python
def test_memory_api_does_not_change_lifecycle_state():
    from production_v2.opportunity.memory import OpportunityMemory
    memory = OpportunityMemory()
    assert hasattr(memory, "load_all")
    assert hasattr(memory, "save")
```

- [ ] **Step 2: Implement `OpportunityMemory` as storage-only**

It accepts and returns lifecycle dictionaries but never decides WATCHING/WAITING/READY/EXECUTED.

- [ ] **Step 3: Make the existing module a compatibility facade**

```python
_default_memory = OpportunityMemory()
load_all = _default_memory.load_all
save = _default_memory.save
backend = _default_memory.backend
last_error = _default_memory.last_error
```

- [ ] **Step 4: Remove direct persistence ownership from `app.py` globals**

The app asks the lifecycle service to persist state; it does not own a second state store.

- [ ] **Step 5: Run persistence and lifecycle tests**

Run: `pytest -q tests/test_production_v2_major_repair.py tests/test_*memory*.py tests/test_*lifecycle*.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/opportunity/memory.py production_v2/opportunity_memory.py production_v2/app.py tests
git commit -m "refactor: isolate opportunity persistence"
```

### Task 4: Make E9 a pure final governance boundary

**Files:**
- Create: `production_v2/governance/final_authority.py`
- Modify: `production_v2/e9_brain.py`
- Modify: `production_v2/pipeline.py`
- Test: E9 contract and decision tests

**Interfaces:**
- Consumes: E1–E8 `EngineResult` values and existing E9 decision semantics.
- Produces: one final `DecisionResult` authorization with explicit execution state.

- [ ] **Step 1: Add tests proving E9 cannot create broker execution**

```python
from production_v2.execution_state import authorize_order, ExecutionState


def test_e9_authorization_is_order_intent_only():
    result = authorize_order(type("R", (), {"decision": "BUY", "gate_passed": True, "execution_state": ExecutionState.NOT_REQUESTED})())
    assert result.execution_state == ExecutionState.ORDER_INTENT
```

- [ ] **Step 2: Extract final decision normalization into the governance module**

Keep all existing hard vetoes, thesis requirements, E7 closed-candle requirements, and E8 economics requirements unchanged.

- [ ] **Step 3: Make `e9_brain.py` call the canonical governance boundary**

E9 remains the only module allowed to produce the final BUY/SELL/NO_TRADE decision.

- [ ] **Step 4: Run E9 contract suite**

Run: `pytest -q tests/test_e9*.py tests/test_production_v2_major_repair.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/governance/final_authority.py production_v2/e9_brain.py production_v2/pipeline.py tests
git commit -m "refactor: isolate e9 final governance"
```

### Task 5: Clean economics, execution, and cross-brain boundaries

**Files:**
- Create: `production_v2/economics/__init__.py`
- Create: `production_v2/execution/__init__.py`
- Modify: `production_v2/profit_edge.py`
- Modify: `production_v2/execution_state.py`
- Modify: `production_v2/pipeline.py`
- Test: economics/execution/contract tests

**Interfaces:**
- Consumes: current profit-edge and execution-state behavior.
- Produces: economics evaluates trade survivability; execution state tracks actual broker state; neither changes E9 authority.

- [ ] **Step 1: Add tests for the boundary**

```python
def test_profit_edge_cannot_open_position():
    from production_v2.profit_edge import evaluate_profit_edge
    result = evaluate_profit_edge(symbol="BTC", regime="TRANSITION", direction="SELL", setup="SETUP", location="PREMIUM", confirmation="PENDING", historical_outcomes=None, realized_rr=1.5, cost_r=0.1)
    assert "execution_state" not in result
```

- [ ] **Step 2: Move execution state helpers under the execution namespace**

Retain compatibility imports from `execution_state.py` until all callers are migrated.

- [ ] **Step 3: Keep `profit_edge.py` calculation-only**

No lifecycle transition and no execution authorization may be introduced into economics.

- [ ] **Step 4: Run focused tests**

Run: `pytest -q tests/test_*profit* tests/test_*execution* tests/test_production_v2_major_repair.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/economics production_v2/execution production_v2/profit_edge.py production_v2/execution_state.py production_v2/pipeline.py tests
git commit -m "refactor: isolate economics and execution boundaries"
```

### Task 6: Remove dead surgery/version runtime dependencies

**Files:**
- Modify/delete only after import search proves safe: `production_v2/bootstrap_surgery.py`, `production_v2/nine_brain_surgery.py`, `production_v2/professional_opportunity_surgery.py`, versioned `e1_professional_core_v*.py`, and other unused migration artifacts.
- Modify: `production_v2/__init__.py` if it exposes legacy modules.
- Test: architecture guardrails.

**Interfaces:**
- Consumes: import graph and test results from Tasks 1–5.
- Produces: production package containing canonical runtime modules without dead runtime mutation layers.

- [ ] **Step 1: Search every legacy symbol before deletion**

Use repository code search for each module/function and inspect all callers.

- [ ] **Step 2: Add/adjust a test forbidding runtime import of removed modules**

```python
import ast
from pathlib import Path


def test_no_legacy_surgery_imports():
    for path in Path("production_v2").glob("*.py"):
        tree = ast.parse(path.read_text())
        names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert all("surgery" not in (name or "") for name in names)
```

- [ ] **Step 3: Delete only modules proven unused**

No deletion is allowed if a production import, test, workflow, or deployment entrypoint still depends on it.

- [ ] **Step 4: Run full tests**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2 tests
 git commit -m "refactor: remove obsolete production v2 surgery layers"
```

### Task 7: Clean CI/workflow surface

**Files:**
- Modify: `.github/workflows/*` only after dependency/use audit.
- Create: `.github/workflows/production-v2-ci.yml` if a single canonical CI workflow is missing.
- Test: GitHub Actions workflow validation via repository CI.

**Interfaces:**
- Consumes: current workflow matrix and tests.
- Produces: one canonical CI path plus only intentionally specialized replay/deployment workflows.

- [ ] **Step 1: Inventory all workflow triggers and referenced scripts**

Do not remove workflows based only on filename age.

- [ ] **Step 2: Consolidate duplicate test workflows**

Preserve major-repair, lifecycle, E1–E9 contract, and no-lookahead coverage in the canonical CI job.

- [ ] **Step 3: Run the canonical workflow**

Expected: dependency installation succeeds and the full Production V2 suite passes.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows
git commit -m "ci: consolidate production v2 verification"
```

### Task 8: Final verification and PR

**Files:**
- Modify: none unless verification exposes a real regression.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified clean-architecture branch ready for review.

- [ ] **Step 1: Run full Python test suite**

Run: `pytest -q`
Expected: 0 failures.

- [ ] **Step 2: Run static import/architecture checks**

Run the architecture guardrail suite and verify no runtime monkey-patching remains.

- [ ] **Step 3: Verify execution semantics**

Prove with tests/log fixtures:

```text
E9 BUY/SELL
  -> ORDER_INTENT
  -> ORDER_SUBMITTED
  -> ACCEPTED
  -> POSITION_OPEN
```

and prove that E9 alone cannot jump to `POSITION_OPEN`.

- [ ] **Step 4: Verify closed-candle/no-lookahead contracts**

Run the existing no-lookahead and closed-candle tests.

- [ ] **Step 5: Verify production import**

Run the equivalent of:

```bash
python -c "import production_v2.app; print('production_v2 import OK')"
```

using the test environment flag where live runtime startup is not desired.

- [ ] **Step 6: Compare branch against `production-v2`**

Confirm only intentional cleanup/refactor files changed and no strategy threshold was reduced.

- [ ] **Step 7: Commit verification-only changes if needed**

```bash
git status --short
git diff --check
```

- [ ] **Step 8: Open PR to `production-v2`**

PR title: `Clean Architecture: Production V2 runtime boundaries`

PR body must list preserved safety invariants and exact verification results. Do not merge until CI is green.
