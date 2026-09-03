# MTF Nine-Engine Coherence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make E1-E9 analyze one coherent market snapshot with explicit M15/M5 responsibilities, reduce redundant vetoes, preserve live opportunities, and expose exactly where trades are blocked.

**Architecture:** M15 is context for E1/E2; M5 is setup/entry for E3/E4/E5/E7/E8; E6 combines both and owns the thesis; E9 performs final governance only. Runtime binding is centralized so bootstrap surgery cannot replace final guards.

**Tech Stack:** Python, Flask/Gunicorn runtime, pytest, existing `EngineResult` contracts, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-03-mtf-nine-engine-coherence-design.md`

## Global Constraints

- One immutable closed-candle snapshot per symbol/evaluation cycle.
- M15 = context; M5 = setup/entry.
- E6 owns thesis; E7 owns confirmation; E8 owns economics; E9 owns final governance.
- WATCHING/WAITING is not NO_OPPORTUNITY.
- Do not lower thresholds, force trades, or treat bootstrap probability as historical evidence.
- Verify with regression tests before deployment claims.

---

### Task 1: Lock final runtime binding order

**Files:**
- Modify: `production_v2/app.py`
- Modify: `production_v2/__init__.py`
- Modify: `production_v2/bootstrap_surgery.py`
- Test: `production_v2/test_runtime_binding_order_regression.py`

**Interfaces:**
- `install_bootstrap_surgery(pipeline_module)` remains callable.
- Final `pipeline_module.analyze_e6`, `analyze_e8`, and `analyze_e9` must be the same objects as the guarded module analyzers after app initialization.

- [ ] **Step 1: Write failing binding regression.**

```python
import os
os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"

from production_v2 import e6_brain, e8_brain, e9_brain
from production_v2 import pipeline as pipeline_module


def test_final_runtime_bindings_use_guarded_analyzers():
    assert pipeline_module.analyze_e6 is e6_brain.analyze_e6
    assert pipeline_module.analyze_e8 is e8_brain.analyze_e8
    assert pipeline_module.analyze_e9 is e9_brain.analyze_e9
```

- [ ] **Step 2: Run the regression and capture the current failure if present.**

Run: `PRODUCTION_V2_DISABLE_LIVE=1 pytest -q production_v2/test_runtime_binding_order_regression.py`

Expected before the fix: at least one assertion fails if a later bootstrap wrapper has replaced a final guard.

- [ ] **Step 3: Make installation order deterministic.** Ensure bootstrap wrappers are installed before final E6/E8/E9 guards, then bind `pipeline_module.analyze_e6/e8/e9` to the final module functions. Do not change trading thresholds.

- [ ] **Step 4: Run the regression again.**

Run: `PRODUCTION_V2_DISABLE_LIVE=1 pytest -q production_v2/test_runtime_binding_order_regression.py`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add production_v2/app.py production_v2/__init__.py production_v2/bootstrap_surgery.py production_v2/test_runtime_binding_order_regression.py
git commit -m "fix(runtime): make final engine guard binding deterministic"
```

### Task 2: Make the snapshot/timeframe contract explicit

**Files:**
- Modify: `production_v2/pipeline.py`
- Modify: relevant market-data/context adapter files discovered during implementation
- Test: `tests/test_mtf_snapshot_contract.py`

**Interfaces:**
- Pipeline evaluation receives one closed-candle snapshot per symbol.
- E1/E2 consume M15 context fields; E3-E5/E7/E8 consume M5 setup fields; E6 receives both through the existing snapshot/result contract.

- [ ] **Step 1: Write failing tests asserting timestamp/snapshot identity and timeframe metadata.**

```python
def test_evaluation_has_one_closed_m5_anchor():
    result = build_test_evaluation()
    assert result["snapshot"]["closed"] is True
    assert result["snapshot"]["m5_timestamp"] == result["engines"]["E3"]["m5_timestamp"]


def test_context_and_setup_timeframes_are_explicit():
    result = build_test_evaluation()
    assert result["engines"]["E1"]["timeframe"] == "M15"
    assert result["engines"]["E2"]["timeframe"] == "M15"
    for key in ("E3", "E4", "E5", "E7", "E8"):
        assert result["engines"][key]["timeframe"] == "M5"
```

- [ ] **Step 2: Run the tests and confirm they fail against the current metadata contract.**

Run: `pytest -q tests/test_mtf_snapshot_contract.py`

- [ ] **Step 3: Implement metadata and snapshot propagation without allowing an engine to fetch a newer candle during the same cycle.**

- [ ] **Step 4: Run the focused tests and existing pipeline regressions.**

Run: `pytest -q tests/test_mtf_snapshot_contract.py tests/test_e6_runtime_binding.py tests/test_e8_applicability_boundary.py`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add production_v2/pipeline.py tests/test_mtf_snapshot_contract.py
git commit -m "feat(pipeline): make M15 context and M5 setup contract explicit"
```

### Task 3: Remove redundant soft vetoes while retaining hard conflicts

**Files:**
- Modify: `production_v2/e6_brain.py`
- Modify: `production_v2/e6_opportunity_guard.py`
- Modify: `production_v2/causal_reconciliation.py`
- Test: `tests/test_soft_disagreement_not_hard_veto.py`

**Interfaces:**
- E6 preserves a thesis when evidence is directionally coherent but E2/E3/E5 contain non-terminal counter-evidence.
- Hard invalidation remains a veto.

- [ ] **Step 1: Write failing fixtures for a coherent M15/M5 opportunity with one soft disagreement.**

```python
def test_soft_counter_evidence_preserves_watch():
    result = analyze_fixture(
        e1={"directional_pressure": "BUY", "trend_state": "UP"},
        e2={"finding": "BUY opportunity is developing"},
        e3={"external_state": "MIXED", "internal_state": "UP"},
        e4={"event": "LOW_SWEEP_REJECTION", "response_actor": "BUYERS", "auction_state": "PENDING"},
        e5={"finding": "FAVORABLE_LOCATION", "value_state": "DISCOUNT", "available_space_atr_long": 1.0},
    )
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["watch_only"] is True
    assert "NO_CAUSAL_OPPORTUNITY" not in result.output["reason_codes"]


def test_terminal_conflict_still_invalidates():
    result = analyze_fixture(
        e1={"directional_pressure": "BUY"},
        e2={"finding": "BUY opportunity"},
        e3={"structure_invalidated": True},
        e4={"event": "HIGH_SWEEP_REJECTION", "response_actor": "SELLERS", "auction_state": "CONFIRMED"},
        e5={"finding": "FAVORABLE_LOCATION", "available_space_atr_long": 1.0},
    )
    assert result.output["setup"] in {"NO_SETUP", "UNKNOWN"} or result.output.get("invalidated") is True
```

- [ ] **Step 2: Run focused tests and verify the new soft-disagreement test fails or exposes the current veto.**

Run: `pytest -q tests/test_soft_disagreement_not_hard_veto.py`

- [ ] **Step 3: Change only soft-veto classification. Do not lower score/quality/RR thresholds.**

- [ ] **Step 4: Run E6 causal and pending-counterflow regressions.**

Run: `pytest -q tests/test_e6_pending_counterflow_inference.py tests/test_causal_reconciliation.py tests/test_opportunity_lifecycle_e6_watch_boundary.py`

- [ ] **Step 5: Commit.**

```bash
git add production_v2/e6_brain.py production_v2/e6_opportunity_guard.py production_v2/causal_reconciliation.py tests/test_soft_disagreement_not_hard_veto.py
git commit -m "fix(e6): distinguish soft counter-evidence from hard invalidation"
```

### Task 4: Make E7/E8/E9 consume the thesis boundary cleanly

**Files:**
- Modify: `production_v2/e7_thesis_boundary.py`
- Modify: `production_v2/e8_applicability_boundary.py`
- Modify: `production_v2/e9_watch_boundary.py`
- Modify: `production_v2/e9_brain.py`
- Test: `tests/test_thesis_confirmation_economics_governance_chain.py`

**Interfaces:**
- E7 returns WAIT when E6 is a watch, confirms only a surviving setup thesis.
- E8 returns NOT_APPLICABLE without running economics when no thesis exists.
- E9 returns WATCH/NO_TRADE for a valid watch, with no fabricated economic blockers.

- [ ] **Step 1: Write the end-to-end boundary regression.**

```python
def test_watch_stops_cleanly_at_e7_without_becoming_economic_failure():
    engines = run_fixture_with_e6_watch()
    assert engines["E7"].output["confirmation"] == "NOT_APPLICABLE"
    assert engines["E8"].output["finding"] == "NOT_APPLICABLE"
    assert engines["E8"].output["reason_codes"] == ["E6_THESIS_REQUIRED"]
    assert engines["E9"].output["final_governance"] == "WATCH"
    assert engines["E9"].output["economic_state"] == "NOT_APPLICABLE"
```

- [ ] **Step 2: Run it and verify the current contradiction is reproduced if still present.**

Run: `pytest -q tests/test_thesis_confirmation_economics_governance_chain.py`

- [ ] **Step 3: Implement the minimum boundary changes and ensure E9 cannot add new blockers to a watch.**

- [ ] **Step 4: Run all E7/E8/E9 boundary regressions.**

Run: `pytest -q tests/test_e7_thesis_boundary.py tests/test_e8_applicability_boundary.py tests/test_e9_watch_boundary.py tests/test_e9_brain.py`

- [ ] **Step 5: Commit.**

```bash
git add production_v2/e7_thesis_boundary.py production_v2/e8_applicability_boundary.py production_v2/e9_watch_boundary.py production_v2/e9_brain.py tests/test_thesis_confirmation_economics_governance_chain.py
git commit -m "fix(governance): preserve clean thesis-to-confirmation boundary"
```

### Task 5: Preserve opportunity lifecycle and expose the first blocking authority

**Files:**
- Modify: `production_v2/opportunity_lifecycle.py`
- Modify: `production_v2/app.py`
- Test: `tests/test_opportunity_blocking_telemetry.py`

**Interfaces:**
- A surviving E6 watch persists across M5 candles.
- Lifecycle remains WAITING until invalidated, confirmed, or executed.
- Each evaluation exposes `first_blocking_authority` as one of `NONE`, `E6`, `E7`, `E8`, `E9` and a machine-readable reason.

- [ ] **Step 1: Write failing telemetry/lifecycle tests.**

```python
def test_waiting_opportunity_persists_and_identifies_first_blocker():
    first = run_closed_candle_fixture(state="WATCH")
    second = run_next_closed_candle_fixture(previous=first)
    assert first["lifecycle"]["state"] == "WAITING"
    assert second["lifecycle"]["state"] == "WAITING"
    assert second["lifecycle"]["opportunity_id"] == first["lifecycle"]["opportunity_id"]
    assert second["lifecycle"]["first_blocking_authority"] in {"E7", "E8", "E9"}
```

- [ ] **Step 2: Run the focused tests and confirm the current lifecycle/telemetry contract is incomplete.**

Run: `pytest -q tests/test_opportunity_blocking_telemetry.py`

- [ ] **Step 3: Implement continuity and blocker telemetry without changing trade thresholds.**

- [ ] **Step 4: Run lifecycle regressions.**

Run: `pytest -q tests/test_opportunity_lifecycle_e6_watch_boundary.py tests/test_opportunity_blocking_telemetry.py`

- [ ] **Step 5: Commit.**

```bash
git add production_v2/opportunity_lifecycle.py production_v2/app.py tests/test_opportunity_blocking_telemetry.py
git commit -m "feat(lifecycle): expose opportunity continuity and first blocker"
```

### Task 6: Full regression, static/runtime verification, and deployment gate

**Files:**
- Modify: `.github/workflows/*` only if existing workflow cannot execute the required suite
- Test: existing `tests/` plus all new regression tests

- [ ] **Step 1: Run the complete production-v2 pytest suite with live runtime disabled.**

Run: `PRODUCTION_V2_DISABLE_LIVE=1 pytest -q`

Expected: PASS with zero failures.

- [ ] **Step 2: Run an import smoke test.**

Run: `PRODUCTION_V2_DISABLE_LIVE=1 python -c "import production_v2; import production_v2.app; print('IMPORT_OK')"`

Expected: `IMPORT_OK` and no live runtime startup.

- [ ] **Step 3: Inspect Git diff for accidental threshold changes.**

Run: `git diff HEAD~6..HEAD -- production_v2 | grep -E 'MIN_SCORE|MIN_RISK_REWARD|SELL_MIN_SCORE|SELL_MIN_PATTERN_QUALITY|SELL_MIN_TRIGGER_QUALITY'`

Expected: no unauthorized threshold relaxation.

- [ ] **Step 4: Run the existing CI workflow and inspect the workflow result.**

Expected: green status for the relevant branch commit. If CI is unavailable, report that fact instead of claiming success.

- [ ] **Step 5: Only after verification, deploy `production-v2` and inspect at least two fresh closed M5 candles for GOLD and BTC.**

Expected healthy GOLD/BTC log shape:

```text
E6 = OPPORTUNITY_WATCH / REAL_SETUP / NO_OPPORTUNITY
E7 = WAIT / CONFIRMED / NOT_APPLICABLE
E8 = NOT_APPLICABLE / ECONOMICALLY_ACCEPTABLE / ECONOMICALLY_INVALID
E9 = WATCH / TRADE / NO_TRADE
lifecycle = IDLE / WAITING / READY / EXECUTED / INVALIDATED
```

- [ ] **Step 6: Commit any workflow-only adjustment separately.**

```bash
git add .github/workflows
git commit -m "ci: verify production-v2 coherence suite"
```
