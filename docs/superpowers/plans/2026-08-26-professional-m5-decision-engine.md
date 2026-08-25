# Professional M5 Decision Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy production execution path with one profitable-opportunity-oriented nine-engine M5 decision pipeline using all defined sub-engines, isolated GOLD/BTC policies, auditable decisions, and identical live/backtest behavior.

**Architecture:** Keep `production_v2` as the application boundary, make the nine engines and their sub-engines the only decision path, and move asset differences into explicit GOLD/BTC policy modules rather than cross-asset fallback. E1-E8 produce structured evidence plus only true hard failures; E9 alone converts the evidence into BUY/SELL/WAIT/NO_TRADE.

**Tech Stack:** Python, Flask, pandas/numpy/scipy as already present, pytest, LSE replay/live service, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-26-professional-m5-decision-engine-design.md`

## Global Constraints

- Production architecture is exactly `E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9`.
- E9 is the sole execution authority.
- `v11/engine.py`, legacy G1/G2/G3, B1/B2/B3 dispatch, and cross-asset fallback must not be reachable from production.
- GOLD and BTC share contracts but never share asset-specific setups, thresholds, or trade logic.
- Hard gates are only for invalid data, invalidated structure/setup/confirmation, invalid risk geometry, minimum RR, exposure, and execution integrity.
- Optional quality evidence contributes to score and must not independently block a trade unless the specification explicitly defines it as a hard invalidation.
- Every closed M5 candle must be auditable.
- Live and backtest must call the same pipeline implementation.
- No profitability claim is allowed until realistic backtest and out-of-sample validation passes.

---

### Task 1: Freeze and verify the canonical contracts

**Files:**
- Modify: `production_v2/contracts.py`
- Modify: `production_v2/engines.py`
- Test: existing `tests/` contract and production-v2 test modules discovered during implementation

**Interfaces:**
- `EngineResult(engine_id, name, gate_passed, score, output, reason_codes)` remains the common engine result contract.
- `DecisionResult` remains the API/backtest decision contract.
- Add explicit fields only when required for auditability; preserve backward-compatible serialization where possible.

- [ ] **Step 1: Write failing tests for canonical engine IDs, order, and decision authority.**

```python
def test_canonical_engine_order_and_authority():
    assert ProductionPipeline.ENGINE_ORDER == ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")
    assert ENGINE_NAMES["E9"] == "Execution Decision Engine"
```

- [ ] **Step 2: Run the focused tests and confirm the current behavior that conflicts with the new contracts.**

Run: `pytest -q tests -k 'production_v2 or contract or engine'`

Expected: current failures or gaps identify the contract changes needed; do not weaken tests to preserve legacy behavior.

- [ ] **Step 3: Implement the canonical contract fields and engine registry.**

The registry must enumerate every E1-E9 sub-engine code already defined in `production_v2/engines.py`, and serialization must retain engine state, reason codes, score, and output.

- [ ] **Step 4: Run the focused tests again.**

Run: `pytest -q tests -k 'production_v2 or contract or engine'`

Expected: PASS for canonical registry/contract tests.

- [ ] **Step 5: Commit.**

```bash
git add production_v2/contracts.py production_v2/engines.py tests
git commit -m "refactor: freeze canonical nine-engine contracts"
```

### Task 2: Make E1-E5 evidence-first instead of over-filtering

**Files:**
- Modify: `production_v2/engines.py`
- Modify: `trading_system/engines/e1/*.py`
- Modify: `trading_system/engines/e2/*.py`
- Modify: `trading_system/engines/e3/*.py`
- Modify: `trading_system/engines/e4/*.py`
- Modify: `trading_system/engines/e5/*.py`
- Test: corresponding engine/sub-engine tests under `tests/`

**Interfaces:**
- Each sub-engine continues returning a state/evidence payload and score.
- `run_engine()` aggregates sub-engine scores without turning every weak/neutral evidence state into a hard failure.
- `_professional_gate()` returns hard failures only for actual invalidity.

- [ ] **Step 1: Add failing tests proving that weak optional evidence produces PASS/WAIT evidence rather than an automatic NO_TRADE.**

```python
def test_e1_non_dominant_but_tradeable_state_is_not_hard_failed(sample_market):
    result = run_engine("E1", sample_market)
    assert "E1_DATA_INVALID" not in result.reason_codes
    assert result.output["1A"]
```

- [ ] **Step 2: Add tests for E5 proving a non-perfect but non-chasing location remains eligible when reward space exists.**

```python
def test_e5_good_enough_location_is_evidence_not_hard_gate(sample_context):
    result = run_engine("E5", sample_context)
    assert "E5_LOCATION_UNCONFIRMED" not in result.reason_codes
```

- [ ] **Step 3: Implement the minimum necessary hard-gate changes.**

Remove hard blocking for directional dominance, perfect alignment, measurable liquidity quality, perfect location quality, and setup maturity when those states represent weak evidence rather than invalidity. Preserve hard invalidation and data integrity checks.

- [ ] **Step 4: Run focused tests.**

Run: `pytest -q tests -k 'e1 or e2 or e3 or e4 or e5'`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add production_v2/engines.py trading_system/engines/e1 trading_system/engines/e2 trading_system/engines/e3 trading_system/engines/e4 trading_system/engines/e5 tests
git commit -m "refactor: convert market context engines to evidence-first gates"
```

### Task 3: Rebuild E6-E7 for actionable M5 setups and confirmation

**Files:**
- Modify: `production_v2/engines.py`
- Modify: `trading_system/engines/e6/*.py`
- Modify: `trading_system/engines/e7/*.py`
- Test: E6/E7 tests under `tests/`

**Interfaces:**
- E6 consumes E1-E5 context and emits setup archetype, direction, maturity, quality, invalidation and evidence score.
- E7 consumes E1-E6 context and emits trigger, trigger quality, follow-through, failure and confirmation score.

- [ ] **Step 1: Write failing tests for the supported professional M5 setup families.**

```python
@pytest.mark.parametrize("archetype", [
    "DIRECTIONAL_SETUP",
    "BREAKOUT_SETUP",
    "RANGE_REJECTION_SETUP",
    "LIQUIDITY_REVERSAL_SETUP",
    "MEAN_REVERSION_SETUP",
])
def test_setup_archetype_can_reach_e6(archetype, context_factory):
    context = context_factory(archetype=archetype)
    result = run_engine("E6", context)
    assert result.output
```

- [ ] **Step 2: Write failing tests showing a real trigger can pass without every optional confirmation feature being present.**

```python
def test_valid_trigger_does_not_require_all_optional_confirmation_features(context_factory):
    result = run_engine("E7", context_factory(trigger=True, optional_filters_missing=True))
    assert result.gate_passed
```

- [ ] **Step 3: Implement setup/confirmation scoring and hard invalidation boundaries.**

Use setup quality, maturity, trigger quality and follow-through as weighted evidence. Only confirmed failure/invalidation becomes a hard block.

- [ ] **Step 4: Run focused tests.**

Run: `pytest -q tests -k 'e6 or e7 or setup or confirmation'`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add production_v2/engines.py trading_system/engines/e6 trading_system/engines/e7 tests
git commit -m "feat: make M5 setup and confirmation actionable"
```

### Task 4: Rebuild E8 risk for short-term profitability geometry

**Files:**
- Modify: `production_v2/engines.py`
- Modify: `trading_system/engines/e8/*.py`
- Test: E8/risk tests under `tests/`

**Interfaces:**
- E8 returns a valid trade plan with direction, entry, structural stop, target(s), risk distance, ATR risk, RR, and sizing/exposure state.
- `risk_policy` is supplied by the asset policy, never by a cross-asset fallback.

- [ ] **Step 1: Add failing tests for minimum RR, structural stop, and valid short-term risk geometry.**

```python
def test_e8_accepts_profitable_geometry(context_factory):
    result = run_engine("E8", context_factory(min_rr=1.5, target_rr=2.0))
    assert result.output["trade_plan"]["valid"]
    assert result.output["trade_plan"]["rr_tp2"] >= 1.5
```

- [ ] **Step 2: Add failing tests proving oversized stops and sub-minimum RR remain hard failures.**

```python
def test_e8_rejects_bad_rr(context_factory):
    result = run_engine("E8", context_factory(min_rr=1.5, target_rr=1.2))
    assert not result.gate_passed
    assert "E8_RR_BELOW_MINIMUM" in result.reason_codes
```

- [ ] **Step 3: Implement asset-independent risk math with policy-driven parameters.**

Keep structural invalidation as the primary stop model. Use target RR as a preferred objective above the minimum. Do not reject a valid trade solely because the target is not the preferred maximum RR.

- [ ] **Step 4: Run focused tests.**

Run: `pytest -q tests -k 'e8 or risk'`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add production_v2/engines.py trading_system/engines/e8 tests
 git commit -m "feat: rebuild M5 risk geometry"
```

### Task 5: Create isolated GOLD and BTC asset policies

**Files:**
- Create: `production_v2/assets/__init__.py`
- Create: `production_v2/assets/gold.py`
- Create: `production_v2/assets/btc.py`
- Modify: `production_v2/pipeline.py`
- Test: `tests/test_asset_policies.py`

**Interfaces:**
- `get_asset_policy(symbol: str) -> AssetPolicy`
- `AssetPolicy` contains only asset-specific setup archetypes, thresholds, risk parameters, and execution constraints.
- No policy may import or invoke the other asset's setup implementation.

- [ ] **Step 1: Write failing isolation tests.**

```python
def test_gold_policy_never_contains_btc_setups():
    assert not any(x.startswith("B") for x in get_asset_policy("GOLD").allowed_setups)


def test_btc_policy_never_contains_gold_setups():
    assert not any(x.startswith("G") for x in get_asset_policy("BTC").allowed_setups)
```

- [ ] **Step 2: Implement the policy interface and explicit GOLD/BTC parameter sets.**

Do not copy the old G1-G3/B1-B3 dispatcher. Translate setup behavior into the E6 archetype contract and asset-specific parameterization.

- [ ] **Step 3: Run isolation tests.**

Run: `pytest -q tests/test_asset_policies.py`

Expected: PASS.

- [ ] **Step 4: Commit.**

```bash
git add production_v2/assets production_v2/pipeline.py tests/test_asset_policies.py
git commit -m "feat: isolate GOLD and BTC trading policies"
```

### Task 6: Remove the legacy runtime decision path

**Files:**
- Modify: `production_v2/service.py`
- Modify: `production_v2/app.py`
- Modify: `production_v2/pipeline.py`
- Modify: Render/startup configuration files discovered during implementation
- Archive or delete only after import audit: `v11/engine.py` and legacy dispatch modules
- Test: `tests/test_no_legacy_runtime.py`

**Interfaces:**
- Live service calls `ProductionPipeline.run()` directly.
- No production import may resolve `v11.engine`, legacy G/B strategy dispatch, or cross-asset fallback.

- [ ] **Step 1: Write failing import-audit tests.**

```python
def test_production_runtime_does_not_import_legacy_modules(monkeypatch):
    import production_v2.service as service
    source = inspect.getsource(service)
    assert "v11.engine" not in source
    assert "cross_asset" not in source.lower()
```

- [ ] **Step 2: Search the repository for every production reference to legacy modules and dispatchers.**

Run: `git grep -n -E 'v11\.engine|cross_asset|evaluate_gold|evaluate_btc|G1|G2|G3|B1|B2|B3' -- production_v2 trading_system .github`

Expected: only explicit archive/reference documentation remains; production imports are zero.

- [ ] **Step 3: Replace the live decision call with the canonical pipeline.**

The live loop must feed normalized closed M5 candles into `ProductionPipeline.run()` and publish only its E9 decision.

- [ ] **Step 4: Run the import audit and production-v2 tests.**

Run: `pytest -q tests -k 'production_v2 or legacy or service'`

Expected: PASS and zero legacy runtime imports.

- [ ] **Step 5: Commit.**

```bash
git add production_v2 tests .github
 git commit -m "refactor: remove legacy runtime decision path"
```

### Task 7: Unify live and backtest execution

**Files:**
- Modify: replay/backtest modules discovered under `replay/`, `backtest/`, or `production_v2/`
- Modify: `.github/workflows/production-v2-tests.yml`
- Create/modify: `tests/test_live_backtest_parity.py`

**Interfaces:**
- Backtest calls the same `ProductionPipeline.run()` used by live service.
- A replay candle produces the same E1-E9 state and decision as live for identical input.

- [ ] **Step 1: Write a parity test using a deterministic candle fixture.**

```python
def test_live_and_backtest_use_same_pipeline(sample_market):
    live = ProductionPipeline().run(sample_market)
    replay = run_replay_once(sample_market)
    assert replay.as_dict() == live.as_dict()
```

- [ ] **Step 2: Implement replay integration through the production-v2 pipeline.**

Remove any separate legacy strategy evaluation from the production-v2 backtest path.

- [ ] **Step 3: Run parity tests.**

Run: `pytest -q tests/test_live_backtest_parity.py`

Expected: PASS.

- [ ] **Step 4: Commit.**

```bash
git add production_v2 replay backtest .github/workflows tests/test_live_backtest_parity.py
 git commit -m "test: unify live and backtest decision paths"
```

### Task 8: Add profitability and over-filtering telemetry

**Files:**
- Modify: `production_v2/statistics.py`
- Modify: `production_v2/pipeline.py`
- Create: `production_v2/telemetry.py`
- Test: `tests/test_gate_telemetry.py`

**Interfaces:**
- `record_candle_audit(decision_result) -> None`
- `build_profitability_report() -> dict`
- Report includes per-engine block counts, per-reason counts, trade outcomes, R statistics, and asset/regime splits.

- [ ] **Step 1: Write failing tests for gate contribution accounting.**

```python
def test_gate_report_counts_blocked_and_traded_outcomes():
    report = build_profitability_report()
    assert "block_rate_by_engine" in report
    assert "expectancy_r" in report
    assert "opportunity_capture_rate" in report
```

- [ ] **Step 2: Implement audit records for every closed candle.**

Store E1-E9 states, sub-engine scores, reason codes, final decision, trade plan, and eventual R outcome without losing WAIT/NO_TRADE observations.

- [ ] **Step 3: Implement per-gate counterfactual analysis where replay data permits it.**

For each hard gate, calculate the outcome distribution of observations it blocked. This identifies gates that remove winners without improving expectancy.

- [ ] **Step 4: Run telemetry tests.**

Run: `pytest -q tests/test_gate_telemetry.py`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add production_v2 tests/test_gate_telemetry.py
 git commit -m "feat: add profitability and gate contribution telemetry"
```

### Task 9: Build the realistic M5 validation suite

**Files:**
- Create: `tests/fixtures/m5_market_scenarios.py`
- Create: `tests/test_professional_m5_validation.py`
- Modify: `.github/workflows/production-v2-tests.yml`
- Modify: validation/reporting scripts discovered during implementation

**Interfaces:**
- Validation produces deterministic metrics for GOLD and BTC independently.
- The suite checks positive expectancy, trade frequency, drawdown, and over-filtering; it does not hard-code a profitable result.

- [ ] **Step 1: Add deterministic scenario fixtures for trend continuation, breakout/retest, liquidity reversal, range rejection, transition, and invalid data.**

- [ ] **Step 2: Add failing assertions for structural requirements.**

```python
def test_professional_m5_report_has_required_metrics(report):
    required = {
        "trades", "win_rate", "expectancy_r", "profit_factor",
        "net_r", "max_drawdown_r", "trades_per_day",
        "opportunity_capture_rate", "block_rate_by_engine",
    }
    assert required <= report.keys()
```

- [ ] **Step 3: Implement the validation runner using realistic costs.**

Use the repository's available spread/slippage/fee configuration and closed-candle-only execution. Never use future candle data to construct a signal.

- [ ] **Step 4: Run deterministic validation.**

Run: `pytest -q tests/test_professional_m5_validation.py`

Expected: PASS for schema and execution correctness. Profitability thresholds are reported, not faked.

- [ ] **Step 5: Commit.**

```bash
git add tests .github/workflows/production-v2-tests.yml
 git commit -m "test: add professional M5 validation suite"
```

### Task 10: Run historical/out-of-sample profitability evaluation

**Files:**
- Modify: existing LSE replay/backtest runner only where required for the canonical pipeline
- Modify: validation report output
- Test/Artifact: GitHub Actions run and report artifact

**Interfaces:**
- Historical evaluation uses the canonical production-v2 pipeline.
- Results are reported separately for GOLD and BTC and by regime.

- [ ] **Step 1: Run the full test suite with live runtime disabled.**

Run: `PRODUCTION_V2_DISABLE_LIVE=1 pytest -q`

Expected: PASS.

- [ ] **Step 2: Run historical replay using the configured `LSE_API_KEY` secret in GitHub Actions.**

The workflow must execute only closed M5 candles and use the same production pipeline as live.

- [ ] **Step 3: Review the report for the following decision criteria.**

A system is accepted as a candidate profitable system only if after costs it has positive expectancy, positive profit factor, acceptable drawdown, and sufficient trade frequency in both the aggregate sample and a reserved out-of-sample period. If one asset fails, do not transfer the other asset's result to it.

- [ ] **Step 4: Compare each hard gate's contribution.**

Any gate that mostly removes eventual winners without materially reducing losses must be relaxed or converted into evidence scoring before the next validation cycle.

- [ ] **Step 5: Commit only code/reporting changes; never commit credentials or fabricated results.**

```bash
git status
git diff --check
git log -1 --oneline
```

### Task 11: Production verification and deployment readiness

**Files:**
- Modify: `production_v2/app.py` only if status/reporting needs final updates
- Modify: deployment/workflow files only for verified configuration
- Test: production smoke tests

**Interfaces:**
- `/` reports `system=9-ENGINE`, `version=production-v2`, `legacy_runtime=false`, and E9 decision authority.
- `/health` reports live runtime state.
- `/statistics` exposes the new profitability/gate telemetry.

- [ ] **Step 1: Run static legacy import audit.**

Run: `git grep -n -E 'v11\.engine|cross_asset|G1|G2|G3|B1|B2|B3' -- production_v2 trading_system .github || true`

Expected: no production execution references.

- [ ] **Step 2: Run syntax and test verification.**

Run: `python -m compileall production_v2 trading_system` and `PRODUCTION_V2_DISABLE_LIVE=1 pytest -q`

Expected: compile succeeds and all tests pass.

- [ ] **Step 3: Run deployment smoke test.**

Start with `gunicorn production_v2.app:app` under a test environment and verify `/`, `/health`, and `/statistics` return the canonical 9-engine metadata.

- [ ] **Step 4: Verify logs on a closed M5 candle.**

Expected log sequence contains E1-E9 states and one final E9 decision, with no legacy strategy dispatcher or cross-asset fallback messages.

- [ ] **Step 5: Commit the verified release.**

```bash
git add production_v2 trading_system .github tests docs
 git commit -m "release: professional M5 nine-engine decision system"
```
