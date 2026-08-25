# No Cross-Asset Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove cross-asset strategy fallback so GOLD and BTC can only generate signals from their own strategy families.

**Architecture:** Keep the existing MTF and native asset-strategy pipelines. Remove the cross-asset branch from both engines; no native candidate means `NO_TRADE`. Shared scoring/regime/risk utilities remain shared but receive only the target asset's data.

**Tech Stack:** Python 3, pandas, pytest, Flask, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-25-no-cross-asset-strategy-design.md`

## Global Constraints

- GOLD strategies: G1/G2/G3 only.
- BTC strategies: B1/B2/B3 only.
- Cross-asset fallback must not participate in live signal decisions.
- MTF remains H1→M15→M5 with H1/M15 closed before M5 trigger.
- Live orders remain disabled.

---

### Task 1: Replace fallback tests with isolation tests

**Files:**
- Modify: `tests/test_cross_asset_fallback.py`
- Test: `tests/test_cross_asset_fallback.py`

- [ ] **Step 1: Replace the old fallback assertions with target-local assertions.**

Use tests that assert `native_strategy_ids("GOLD", regime)` contains only G engines and `native_strategy_ids("BTC", regime)` contains only B engines. Add assertions that the opposite family is absent for multiple regimes.

- [ ] **Step 2: Add an engine-source isolation test.**

Assert the source/strategy family contract directly: GOLD allowed engines are `G1/G2/G3`; BTC allowed engines are `B1/B2/B3`.

- [ ] **Step 3: Run the focused test.**

Run: `pytest -q tests/test_cross_asset_fallback.py`
Expected before implementation: the old cross-fallback expectations fail after the test replacement until engine changes are complete.

---

### Task 2: Remove cross-asset fallback from BTC engine

**Files:**
- Modify: `v11/engine.py`
- Test: `tests/test_btc_strategy_dispatch.py`

- [ ] **Step 1: Remove the `evaluate_cross_asset_fallback` import.**

- [ ] **Step 2: Change the BTC strategy-selection branch.**

Evaluate `evaluate_btc_strategies(m5, regime)` only. If it returns no candidates, return `NO_TRADE` with the existing BTC-native rejection reason. Do not inspect GOLD strategies.

- [ ] **Step 3: Set BTC metadata to native-only.**

`strategy_selection_order` becomes `["NATIVE"]`; `strategy_mode` is `NATIVE` when a setup is selected and `NONE` when there is no candidate; `source_asset` remains `BTC`.

- [ ] **Step 4: Add a regression assertion that BTC cannot emit a G engine.**

- [ ] **Step 5: Run focused BTC tests.**

Run: `pytest -q tests/test_btc_strategy_dispatch.py tests/test_v11_engine.py tests/test_v12_1_mtf.py`
Expected: PASS.

---

### Task 3: Remove cross-asset fallback from GOLD engine

**Files:**
- Modify: `v11/engine_gold.py`
- Test: `tests/test_gold_g3_smc.py`

- [ ] **Step 1: Remove the `evaluate_cross_asset_fallback` import.**

- [ ] **Step 2: Change GOLD strategy selection to native-only.**

Evaluate `evaluate_asset_strategies("GOLD", m5, regime)` only. If no candidates pass, return `NO_TRADE`; never evaluate B strategies.

- [ ] **Step 3: Set GOLD metadata to native-only.**

`strategy_selection_order` becomes `["NATIVE"]`; `strategy_mode` is `NATIVE` for a selected setup and `NONE` otherwise; `source_asset` is `GOLD`.

- [ ] **Step 4: Add a regression assertion that GOLD cannot emit a B engine.**

- [ ] **Step 5: Run focused GOLD tests.**

Run: `pytest -q tests/test_gold_g3_smc.py tests/test_v11_strategies.py tests/test_v11_strategy_filters.py`
Expected: PASS.

---

### Task 4: Remove obsolete fallback implementation and validate the full suite

**Files:**
- Delete: `v11/cross_asset_fallback.py`
- Modify: `.github/workflows/asset-strategy-architecture.yml` only if the deleted module is referenced
- Modify: tests that import the deleted module

- [ ] **Step 1: Search the repository for `cross_asset_fallback`, `CROSS_ASSET`, and `strategy_origin`.**

- [ ] **Step 2: Remove all active imports/usages and update tests/docs that describe cross-asset fallback as supported behavior.**

- [ ] **Step 3: Run the complete test suite.**

Run: `pytest -q`
Expected: PASS with no cross-asset fallback tests remaining.

- [ ] **Step 4: Compile the active engine modules.**

Run: `python -m py_compile v11/engine.py v11/engine_gold.py v11/asset_strategies.py v11/regime.py`
Expected: exit code 0.

- [ ] **Step 5: Search once more for forbidden live-path markers.**

Run: `grep -R "CROSS_ASSET\|evaluate_cross_asset_fallback\|cross_asset_fallback" v11 tests --exclude-dir=__pycache__`
Expected: no active references; only historical documentation may remain if explicitly marked historical.
