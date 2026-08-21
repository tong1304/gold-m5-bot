# Real-Money Validation v5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the XAU/USD M5 engine conservative enough to evaluate trading edge after realistic costs, OHLC intrabar ambiguity, complete outcome accounting, and live risk guards.

**Architecture:** Preserve the existing pattern/filter/score engine while adding a focused execution-and-risk layer around trade simulation and live signal validation. Keep the current Flask API compatible, sanitize public errors, and expose complete performance accounting including TIMEOUT and net expectancy.

**Tech Stack:** Python, Flask, pandas, existing `engine_v42.py`, pytest, GitHub Actions if present.

**Spec:** `docs/superpowers/specs/2026-08-22-real-money-validation-v5-design.md`

## Global Constraints

- Do not introduce broker-order execution; this remains a signal/paper-validation engine.
- Do not call model score a probability.
- Do not remove existing pattern/regime/location/momentum logic unless required for correctness.
- Do not hide TIMEOUT from outcome distributions or primary expectancy.
- Do not expose traceback or exception type in public API responses.
- Preserve existing public endpoints and symbol query compatibility.
- Prefer conservative assumptions when OHLC data cannot reveal intrabar order.

---

### Task 1: Establish regression-test harness and inspect current behavior

**Files:**
- Create: `tests/test_v5_validation.py`
- Modify: none

**Interfaces:**
- Tests import the existing engine functions directly.
- Later tasks must keep the tested function names compatible or update this test module in the same task.

- [ ] **Step 1: Write focused failing tests for the required public invariants**

```python
import engine_v42 as engine


def test_timeout_is_present_in_outcome_distribution():
    assert "TIMEOUT" in {"WIN", "LOSS", "BREAKEVEN", "TIMEOUT"}


def test_public_error_payload_contract_has_no_traceback():
    assert "trace" not in {"status": "error", "message": "Internal server error"}
```

- [ ] **Step 2: Run the focused tests**

Run: `pytest -q tests/test_v5_validation.py`
Expected: PASS for the baseline contract tests.

- [ ] **Step 3: Commit the test harness**

```bash
git add tests/test_v5_validation.py
git commit -m "test: add v5 validation regression harness"
```

### Task 2: Add explicit execution-cost and outcome helpers

**Files:**
- Modify: `engine_v42.py`
- Test: `tests/test_v5_validation.py`

**Interfaces:**
- Add `calculate_execution_price(raw_price, side, spread, slippage, is_entry)` returning a float.
- Add `classify_trade_outcome(...)` or an equivalent internal helper that returns exactly `WIN`, `LOSS`, `BREAKEVEN`, or `TIMEOUT`.
- Preserve `simulate_trade(...)` as the compatibility entry point.

- [ ] **Step 1: Add failing tests for side-aware execution prices**

```python
def test_buy_entry_is_above_reference_and_sell_entry_below_reference():
    buy = engine.calculate_execution_price(100.0, "BUY", 0.20, 0.05, True)
    sell = engine.calculate_execution_price(100.0, "SELL", 0.20, 0.05, True)
    assert buy > 100.0
    assert sell < 100.0
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest -q tests/test_v5_validation.py::test_buy_entry_is_above_reference_and_sell_entry_below_reference`
Expected: FAIL until the helper exists.

- [ ] **Step 3: Implement the minimal side-aware helper and wire it into `simulate_trade`**

BUY entry uses Ask-side cost and BUY exit uses Bid-side cost. SELL entry uses Bid and SELL exit uses Ask. Apply slippage consistently in the adverse direction. Record modeled cost in the returned trade object.

- [ ] **Step 4: Add a regression test proving exit costs can turn a marginal target into a non-win**

```python
def test_exit_cost_is_applied_before_declaring_target_hit():
    exit_price = engine.calculate_execution_price(100.10, "BUY", 0.20, 0.05, False)
    assert exit_price < 100.10
```

- [ ] **Step 5: Run all execution tests**

Run: `pytest -q tests/test_v5_validation.py -k 'execution or target'`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine_v42.py tests/test_v5_validation.py
git commit -m "fix: model bid ask execution costs"
```

### Task 3: Make TIMEOUT and expectancy first-class performance metrics

**Files:**
- Modify: `engine_v42.py`
- Test: `tests/test_v5_validation.py`

**Interfaces:**
- Preserve `run_backtest(...)` return shape while adding `outcome_counts`, `timeout_percent`, `net_expectancy_r`, `gross_expectancy_r`, and `cost_r`.
- `historical_probability` may remain a resolved-win metric, but it must never be the only primary performance metric.

- [ ] **Step 1: Write a failing accounting test**

```python
def test_timeout_is_not_removed_from_primary_expectancy():
    outcomes = ["WIN", "LOSS", "BREAKEVEN", "TIMEOUT"]
    assert len(outcomes) == 4
```

- [ ] **Step 2: Implement complete outcome counters in the backtest accumulator**

Ensure every resolved trade increments exactly one outcome bucket and timeout trades remain in total-trade denominators.

- [ ] **Step 3: Implement expectancy from all four outcomes**

Use configured R outcomes and costs. Keep resolved probability separately labeled as resolved win rate, and add a warning whenever sample size is below `MIN_HISTORICAL_SAMPLE`.

- [ ] **Step 4: Add tests for a known four-outcome sample**

```python
def test_four_outcome_distribution_is_complete():
    stats = {"WIN": 2, "LOSS": 1, "BREAKEVEN": 1, "TIMEOUT": 1}
    assert sum(stats.values()) == 5
```

- [ ] **Step 5: Run the accounting tests**

Run: `pytest -q tests/test_v5_validation.py -k 'timeout or expectancy or outcome'`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine_v42.py tests/test_v5_validation.py
git commit -m "fix: include timeout in performance accounting"
```

### Task 4: Make intrabar and break-even simulation conservative

**Files:**
- Modify: `engine_v42.py`
- Test: `tests/test_v5_validation.py`

**Interfaces:**
- Preserve `simulate_trade` output compatibility.
- Add explicit trade fields such as `be_state`, `intrabar_assumption`, and `barrier_order_assumption`.

- [ ] **Step 1: Write failing tests for ambiguous candle handling**

```python
def test_ambiguous_barrier_candle_is_not_assumed_to_hit_tp_first():
    assert engine.INTRABAR_AMBIGUITY_POLICY in {"STOP_FIRST", "CONSERVATIVE"}
```

- [ ] **Step 2: Implement a named conservative intrabar policy**

When candle OHLC touches both relevant barriers without tick order, assume the adverse barrier first. Document this in backtest output.

- [ ] **Step 3: Implement break-even as a state transition**

Do not convert an MFE observation into a free intrabar BE move. Activation occurs only under the configured candle-close rule, and any same-candle ambiguity uses the conservative policy.

- [ ] **Step 4: Add tests for BE state transitions**

Verify a trade cannot move to BE merely because a candle high/low exceeded `BREAK_EVEN_R` if the configured activation rule requires candle close.

- [ ] **Step 5: Run the tests**

Run: `pytest -q tests/test_v5_validation.py -k 'intrabar or break_even'`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine_v42.py tests/test_v5_validation.py
git commit -m "fix: use conservative intrabar and breakeven simulation"
```

### Task 5: Harden SL/TP validation and cost-aware R:R

**Files:**
- Modify: `engine_v42.py`
- Test: `tests/test_v5_validation.py`

**Interfaces:**
- Preserve `calculate_trade_levels(...)`.
- Add a validation result such as `validate_trade_levels(...)` returning `valid`, `risk`, `reward`, `effective_rr`, and `reason`.

- [ ] **Step 1: Write failing tests for invalid compressed stops and post-cost R:R**

```python
def test_trade_levels_reject_non_positive_risk():
    result = engine.validate_trade_levels(100.0, 100.0, 101.0, 0.20, 0.05)
    assert result["valid"] is False
```

- [ ] **Step 2: Implement validation**

Reject zero/negative risk, invalid price ordering, and effective reward/risk below `MIN_RISK_REWARD` after modeled costs. Report whether the stop was constrained by ATR or structure.

- [ ] **Step 3: Add tests for a valid level set**

Verify valid BUY and SELL level ordering and effective R:R.

- [ ] **Step 4: Run level tests**

Run: `pytest -q tests/test_v5_validation.py -k 'level or rr or stop'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine_v42.py tests/test_v5_validation.py
git commit -m "fix: validate cost aware trade levels"
```

### Task 6: Add live data freshness, spread, jump and account-risk guards

**Files:**
- Modify: `engine_v42.py`, `app.py`
- Test: `tests/test_v5_validation.py`

**Interfaces:**
- Add `evaluate_live_risk_guard(...)` returning `allowed`, `reasons`, and current guard measurements.
- Expose environment-configurable limits for max spread, max slippage, stale seconds, max price jump, daily loss R, consecutive losses, and max trades/day.
- `/signal` must return `NO_TRADE` with a machine-readable `risk_guard` when blocked.

- [ ] **Step 1: Write failing guard tests**

```python
def test_guard_blocks_excessive_spread():
    result = engine.evaluate_live_risk_guard(spread=1.0, max_spread=0.5)
    assert result["allowed"] is False
    assert "SPREAD_TOO_HIGH" in result["reasons"]
```

- [ ] **Step 2: Implement guard checks**

Check stale candle/data age, excessive spread, excessive price movement from reference, daily loss R, consecutive losses, and trade count. Fail closed when required market-quality inputs are missing.

- [ ] **Step 3: Wire guard into `/signal` before Telegram notification**

A blocked signal must never send a trade alert. Return `signal=NO_TRADE` and include the exact blocking reasons.

- [ ] **Step 4: Add tests for each kill switch**

Cover stale data, price jump, daily loss, consecutive loss, and max trades/day.

- [ ] **Step 5: Run guard tests**

Run: `pytest -q tests/test_v5_validation.py -k 'guard or stale or spread or loss or jump'`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine_v42.py app.py tests/test_v5_validation.py
git commit -m "feat: add live risk and market quality guards"
```

### Task 7: Add walk-forward/out-of-sample reporting

**Files:**
- Modify: `engine_v42.py`
- Test: `tests/test_v5_validation.py`

**Interfaces:**
- Add `run_walk_forward_backtest(df, train_bars, test_bars, step_bars)` returning per-window results and aggregate out-of-sample metrics.
- Add `sample_adequacy` metadata to calibration/performance summaries.

- [ ] **Step 1: Write failing windowing test**

```python
def test_walk_forward_windows_do_not_overlap_training_and_test_ranges():
    windows = engine.build_walk_forward_windows(1000, 400, 200, 200)
    for window in windows:
        assert window["train_end"] <= window["test_start"]
```

- [ ] **Step 2: Implement deterministic window construction**

Use contiguous chronological windows. Never use future bars in the training/calibration segment for an earlier test segment.

- [ ] **Step 3: Implement OOS aggregation**

Aggregate outcome counts, net expectancy, drawdown, and directional/regime performance only from test segments. Mark insufficient windows instead of treating them as evidence.

- [ ] **Step 4: Add score calibration labels**

Keep score separate from probability and require minimum samples before reporting empirical rates for score buckets.

- [ ] **Step 5: Run OOS tests**

Run: `pytest -q tests/test_v5_validation.py -k 'walk_forward or out_of_sample or calibration'`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine_v42.py tests/test_v5_validation.py
git commit -m "feat: add walk forward validation"
```

### Task 8: Sanitize production errors and isolate symbol configuration

**Files:**
- Modify: `app.py`
- Test: `tests/test_v5_validation.py`

**Interfaces:**
- Public error responses contain `status`, `engine_version`, `symbol`, and a safe `message` only.
- Internal traceback is logged server-side.

- [ ] **Step 1: Write failing error-sanitization test**

```python
def test_public_error_payload_has_no_internal_exception_details():
    payload = {"status": "error", "message": "Internal server error"}
    assert "trace" not in payload
    assert "exception_type" not in payload
```

- [ ] **Step 2: Replace public traceback serialization**

Log `traceback.format_exc()` server-side and return a stable safe message to clients. Apply the same policy in Flask handlers, middleware failures, and diagnostics.

- [ ] **Step 3: Add symbol-isolation regression test**

Exercise `?symbol=XAU/USD` followed by `?symbol=BTC/USD` and verify the previous configuration is restored after each request, including exceptions.

- [ ] **Step 4: Run API contract tests**

Run: `pytest -q tests/test_v5_validation.py -k 'error or symbol or middleware'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_v5_validation.py
git commit -m "fix: sanitize errors and harden symbol isolation"
```

### Task 9: Integrate reporting and update version/configuration

**Files:**
- Modify: `app.py`, `engine_v42.py`
- Test: `tests/test_v5_validation.py`

**Interfaces:**
- Engine version becomes `5.0` only after all validation tests pass.
- `/health` and `/` identify the new validation engine and expose safety policy names without secrets.
- `/backtest` exposes complete outcome distribution, net expectancy, cost summary, and OOS summary where configured.

- [ ] **Step 1: Add route-level tests for the response contract**

Verify `/`, `/health`, and `/signal` include version, candle state, risk guard status, and no sensitive exception data.

- [ ] **Step 2: Implement reporting integration**

Keep existing fields for compatibility and append v5 fields. Do not rename existing fields unless a field is misleading; in that case add a clearly named replacement and retain the old field for compatibility.

- [ ] **Step 3: Set engine version to `5.0` and update warnings**

The warning must explicitly say that this is a candle-based validation model and is not broker-execution confirmation.

- [ ] **Step 4: Run the full test suite**

Run: `pytest -q`
Expected: PASS with zero failures.

- [ ] **Step 5: Commit**

```bash
git add app.py engine_v42.py tests/test_v5_validation.py
git commit -m "feat: integrate real money validation v5"
```

### Task 10: Verify repository behavior and CI before declaring completion

**Files:**
- Modify: only if verification finds a concrete defect.

- [ ] **Step 1: Run syntax/import checks**

Run: `python -m py_compile app.py engine_v42.py`
Expected: exit code 0.

- [ ] **Step 2: Run tests**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 3: Run the existing endpoints against safe test data/configuration**

Verify `/health`, `/test-data`, `/diagnostics`, and `/backtest` return JSON and that no traceback is exposed.

- [ ] **Step 4: Inspect the final diff for accidental API/config/secrets changes**

Check that no API keys, tokens, credentials, or local paths were added. Confirm only intended files changed.

- [ ] **Step 5: Push final changes through GitHub and report exact commit SHA**

The final response must distinguish code/test completion from readiness for real-money broker execution. The latter remains `NO-GO` until broker-specific execution validation is completed.
