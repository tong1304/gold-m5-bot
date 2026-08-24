# Multi-Strategy Regime Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make V11 strategy entries more selective and regime-aware so each strategy operates only in market conditions appropriate to its setup, without weighted confluence or changes to the structure-first risk engine.

**Architecture:** Add a small deterministic regime/evidence helper to the V11 strategy layer, pass that context to existing independent strategy contracts, and strengthen the four strategies that need it: LIQUIDITY_SWEEP, TREND_PULLBACK, VWAP_MEAN_REVERSION, and OPENING_RANGE_BREAKOUT. Keep selection deterministic and keep `v11/risk.py` unchanged.

**Tech Stack:** Python 3, pandas, NumPy, pytest/unittest, Flask/Gunicorn, existing V11 engine.

**Spec:** `docs/superpowers/specs/2026-08-24-multi-strategy-regime-filters-design.md`

## Global Constraints

- No weighted confluence or composite strategy score.
- Preserve V11 structure-first SL and nearest-structure TP1/RR validation.
- Use normalized ATR/structure measures; do not hard-code BTC/GOLD absolute prices.
- Do not optimize thresholds from only the 2026-08-23 sample.
- Preserve existing strategy names, replay trade-history schema, and JSON-safe API output.
- Valid setup may still produce NO_TRADE when risk/structure validation rejects it.

---

### Task 1: Add deterministic regime/evidence helpers

**Files:**
- Create: `v11/regime.py`
- Test: `tests/test_v11_regime.py`

**Interfaces:**
- Produces `build_regime_context(m5: pandas.DataFrame, m15: pandas.DataFrame) -> dict`.
- Returned dict contains `m15_direction`, `atr`, `range_ratio`, `compression_ratio`, `trend_strength`, `vwap`, `vwap_distance_atr`, `body_ratio`, `upper_wick_ratio`, `lower_wick_ratio` where data permits, with finite numeric values or `None`.

- [ ] **Step 1: Write failing tests for deterministic range/trend metrics**

```python
def test_build_regime_context_exposes_normalized_metrics():
    ctx = build_regime_context(trending_m5, trending_m15)
    assert ctx["m15_direction"] in {"BUY", "SELL", "NEUTRAL"}
    assert ctx["atr"] > 0
    assert 0 <= ctx["body_ratio"] <= 1
    assert ctx["range_ratio"] >= 0
```

- [ ] **Step 2: Run `pytest tests/test_v11_regime.py -q` and verify the new module/test fails because the helper does not exist.**

- [ ] **Step 3: Implement `build_regime_context()` using existing V11 EMA/ATR utilities and rolling OHLC measurements; avoid external dependencies.**

- [ ] **Step 4: Run `pytest tests/test_v11_regime.py -q` and verify PASS.**

- [ ] **Step 5: Commit with `feat: add v11 regime context helpers`.**

---

### Task 2: Strengthen strategy-specific gates

**Files:**
- Modify: `v11/strategies/multi_strategy.py`
- Test: `tests/test_v11_strategy_filters.py`

**Interfaces:**
- Existing strategy functions retain signatures `(m5, direction, ctx)` and `StrategyResult` output.
- `ctx["regime"]` contains the Task 1 regime dictionary.

- [ ] **Step 1: Write failing tests for each rejected market condition.**

```python
def test_liquidity_sweep_rejects_strong_continuation_against_reversal():
    result = liquidity_sweep(sweep_then_continue_against_reversal, "BUY", {"m15": {"direction": "SELL"}, "regime": regime})
    assert result.status == "FAIL"


def test_trend_pullback_rejects_nearby_opposing_structure():
    result = trend_pullback(trend_pullback_with_resistance_too_close, "BUY", {"m15": {"direction": "BUY"}, "regime": regime})
    assert result.status == "FAIL"


def test_vwap_reversion_rejects_trend_continuation():
    result = vwap_mean_reversion(trending_extension, "BUY", {"m15": {"direction": "NEUTRAL"}, "regime": regime})
    assert result.status == "FAIL"


def test_opening_range_rejects_wick_only_breakout_and_extended_entry():
    result = opening_range_breakout(wick_only_orb_breakout, "BUY", {"m15": {"direction": "BUY"}, "regime": regime})
    assert result.status == "FAIL"
```

- [ ] **Step 2: Run the focused tests and verify they fail against the current permissive strategy rules.**

- [ ] **Step 3: Implement the minimal gates:**
  - `LIQUIDITY_SWEEP`: require sweep/reclaim/rejection and reject strong continuation against the reversal.
  - `TREND_PULLBACK`: require trend alignment, pullback/EMA interaction, continuation body, and adequate opposing-structure distance.
  - `VWAP_MEAN_REVERSION`: require neutral M15/range context, sufficient ATR-normalized VWAP deviation, rejection toward VWAP, and no strong continuation signature.
  - `OPENING_RANGE_BREAKOUT`: require valid range compression, close outside range, meaningful body, and reject excessive extension from the range boundary.

- [ ] **Step 4: Run `pytest tests/test_v11_strategy_filters.py -q` and verify PASS.**

- [ ] **Step 5: Commit with `feat: harden v11 strategy-specific regime filters`.**

---

### Task 3: Thread regime context through V11 engine without changing selection or risk

**Files:**
- Modify: `v11/engine.py`
- Modify: `tests/test_engine_v11.py` if present, otherwise create `tests/test_engine_v11.py`

**Interfaces:**
- `analyze()` continues returning the current response keys, adding `regime` as a diagnostic field.
- `selection.select()` remains unchanged.
- `v11.risk.calculate()` remains unchanged.

- [ ] **Step 1: Write failing engine regression tests proving regime context reaches candidates and weighted confluence is absent.**

```python
def test_engine_attaches_regime_and_keeps_independent_candidates():
    result = engine.analyze(m5, m15, "BTC", index=None)
    assert "regime" in result
    assert all("score" not in c for c in result.get("strategy_candidates", []))


def test_engine_keeps_structure_risk_contract():
    result = engine.analyze(m5, m15, "BTC", index=None)
    assert "trade_levels" in result
    if result["trade_levels"].get("valid"):
        assert result["trade_levels"]["rr"] >= engine.MIN_RISK_REWARD
```

- [ ] **Step 2: Run focused tests and verify failure before engine wiring.**

- [ ] **Step 3: Import `build_regime_context`, construct it once per `analyze()` call, pass it under `ctx["regime"]` to every strategy, and expose it in the top-level result.**

- [ ] **Step 4: Run `pytest tests/test_engine_v11.py tests/test_v11_strategy_filters.py tests/test_v11_regime.py -q` and verify PASS.**

- [ ] **Step 5: Commit with `feat: pass regime context through v11 engine`.**

---

### Task 4: Preserve replay/statistics compatibility and add regression coverage

**Files:**
- Modify: `v11/replay.py` only if the current payload drops the new diagnostic field; otherwise no production replay change.
- Test: `tests/test_replay_strategy_filters.py`

**Interfaces:**
- Replay trade rows retain `time`, `symbol`, `side`, `strategy`, `entry`, `sl`, `tp1`, `tp2`, `tp3`, `rr`, `result`, `r`, and `exit_time` fields already consumed by Statistics.
- No NO_TRADE row is converted into a trade merely because a strategy passes a filter.

- [ ] **Step 1: Write failing replay compatibility tests for strategy identity and actual-trade filtering.**

```python
def test_replay_keeps_actual_trade_schema():
    payload = replay_result
    for trade in payload["trades"]:
        assert {"symbol", "side", "strategy", "entry", "sl", "rr", "result", "r"}.issubset(trade)


def test_replay_does_not_count_no_trade_as_trade():
    assert payload["trades"] == [t for t in payload["trades"] if t.get("side") in {"BUY", "SELL"}]
```

- [ ] **Step 2: Run the focused replay tests and verify the expected contract.**

- [ ] **Step 3: Make only compatibility fixes required to preserve the existing Statistics payload; do not alter trade outcome accounting.**

- [ ] **Step 4: Run replay/statistics regression tests and verify PASS.**

- [ ] **Step 5: Commit with `test: preserve replay strategy statistics contract`.**

---

### Task 5: Run full regression suite and inspect deployment-critical paths

**Files:**
- Modify only files required by failing tests.

- [ ] **Step 1: Run the complete test suite with `pytest -q`.**

- [ ] **Step 2: If failures occur, classify each as regression vs. outdated legacy test and update only tests whose expected contract is intentionally changed by this design.**

- [ ] **Step 3: Run the focused V11 tests again after any compatibility fixes.**

- [ ] **Step 4: Verify Flask imports with `python -c "import app; print(app.v11_engine.ENGINE_VERSION)"`.**

- [ ] **Step 5: Verify no risk.py changes were introduced with `git diff -- v11/risk.py`; expected output is empty.**

- [ ] **Step 6: Commit the final verified changes with `test: verify v11 multi-strategy hardening`.**

## Verification Matrix

| Requirement | Verification |
|---|---|
| No weighted confluence | Search strategy/engine output for composite score logic; candidate tests assert no score field |
| Strategy-specific gates | `tests/test_v11_strategy_filters.py` |
| Regime context | `tests/test_v11_regime.py` |
| Risk unchanged | diff check + existing risk tests |
| Replay schema preserved | `tests/test_replay_strategy_filters.py` + existing replay tests |
| API import/deploy safety | Flask import command |
| Full regression | `pytest -q` |
