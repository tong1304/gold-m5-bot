# E9 Adaptive Professional Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add passive replay-based learning to E9 so decisions become auditable samples and later outcomes become calibration evidence without autonomous rule mutation.

**Architecture:** Add a small learning subsystem with three responsibilities: decision journal, delayed outcome evaluation, and calibration statistics. E9 writes a decision snapshot; future M5 candles resolve it; calibration aggregates immutable samples by asset/regime/evidence signature. Live decisions can read calibration statistics only as advisory evidence.

**Tech Stack:** Python 3, dataclasses, JSON/JSONL persistence, pytest, existing `production_v2` contracts.

**Spec:** `docs/superpowers/specs/2026-08-26-e9-adaptive-learning-design.md`

## Global Constraints

- E1-E8 remain parallel specialists and never become gates.
- E9 remains the only final decision authority.
- GOLD and BTC statistics must remain isolated.
- No look-ahead data may enter the original decision snapshot.
- Minimum sample size is required before calibration becomes meaningful.
- Learning must not mutate live thresholds, risk limits, or order permissions.
- Ambiguous same-candle target/stop ordering is recorded as AMBIGUOUS.
- Live order execution is unchanged.

---

### Task 1: Decision journal contract

**Files:**
- Create: `production_v2/e9_learning.py`
- Test: `tests/test_e9_learning.py`

**Interfaces:**
- Produces `DecisionRecord`, `OutcomeRecord`, `make_decision_record`, `evidence_signature`.
- Consumes the E9 output dictionary and current closed-candle context.

- [ ] **Step 1: Write the failing tests**

```python
from production_v2.e9_learning import make_decision_record, evidence_signature

def test_decision_record_contains_no_future_outcome():
    r = make_decision_record("GOLD", "2026-08-26T05:10:00Z", 4650.0, {"decision":"BUY","thesis_quality":82})
    assert r.asset == "GOLD"
    assert r.decision == "BUY"
    assert r.outcome is None
    assert r.decision_timestamp == "2026-08-26T05:10:00Z"

def test_signature_is_deterministic_and_asset_local():
    e={"direction":"BUY","market_state":"TREND_UP","regime":"TREND","setup":"PULLBACK","confirmation":"CONFIRMED"}
    assert evidence_signature(e) == evidence_signature(dict(e))
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `pytest tests/test_e9_learning.py -q`
Expected: FAIL because `production_v2.e9_learning` does not yet exist.

- [ ] **Step 3: Implement immutable record types**

```python
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass(frozen=True)
class DecisionRecord:
    sample_id: str
    asset: str
    decision_timestamp: str
    candle_timestamp: str
    entry: float | None
    direction: str
    thesis_quality: float
    evidence_signature: str
    outcome: Optional[str] = None
    outcome_timestamp: Optional[str] = None
    realized_r: Optional[float] = None
    mfe_r: Optional[float] = None
    mae_r: Optional[float] = None
    bars_to_resolution: Optional[int] = None
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `pytest tests/test_e9_learning.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/e9_learning.py tests/test_e9_learning.py
git commit -m "feat: add E9 decision learning records"
```

### Task 2: Delayed outcome evaluator

**Files:**
- Modify: `production_v2/e9_learning.py`
- Test: `tests/test_e9_learning.py`

**Interfaces:**
- Produces `evaluate_outcome(record, candles, horizon_bars, target, stop)` returning an `OutcomeRecord`.

- [ ] **Step 1: Write the failing tests**

```python
from production_v2.e9_learning import evaluate_outcome

def test_buy_target_before_stop_is_win():
    candles=[{"high":101,"low":99},{"high":103,"low":100}]
    o=evaluate_outcome("BUY",100,99,103,candles,2)
    assert o.outcome == "WIN"
    assert o.realized_r == 3.0

def test_same_candle_target_and_stop_is_ambiguous():
    candles=[{"high":104,"low":98}]
    o=evaluate_outcome("BUY",100,99,103,candles,1)
    assert o.outcome == "AMBIGUOUS"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_e9_learning.py -q`
Expected: FAIL because `evaluate_outcome` is not implemented.

- [ ] **Step 3: Implement conservative path evaluation**

```python
def evaluate_outcome(direction, entry, stop, target, candles, horizon):
    risk=abs(entry-stop)
    for i,c in enumerate(candles[:horizon],1):
        hit_target = c["high"] >= target if direction == "BUY" else c["low"] <= target
        hit_stop = c["low"] <= stop if direction == "BUY" else c["high"] >= stop
        if hit_target and hit_stop:
            return OutcomeRecord("AMBIGUOUS", None, None, None, i)
        if hit_target:
            r=abs(target-entry)/risk if direction == "BUY" else abs(entry-target)/risk
            return OutcomeRecord("WIN", r, r, 0.0, i)
        if hit_stop:
            return OutcomeRecord("LOSS", -1.0, 0.0, -1.0, i)
    return OutcomeRecord("TIMEOUT", 0.0, None, None, min(len(candles),horizon))
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_e9_learning.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/e9_learning.py tests/test_e9_learning.py
git commit -m "feat: evaluate delayed E9 outcomes conservatively"
```

### Task 3: Calibration statistics

**Files:**
- Create: `production_v2/e9_calibration.py`
- Test: `tests/test_e9_calibration.py`

**Interfaces:**
- Produces `CalibrationStats`, `aggregate_samples(samples, min_samples=30)`, `calibration_key(record)`.

- [ ] **Step 1: Write the failing tests**

```python
from production_v2.e9_calibration import aggregate_samples

def test_small_sample_is_not_actionable():
    samples=[{"asset":"GOLD","outcome":"WIN","realized_r":2.0} for _ in range(3)]
    stats=aggregate_samples(samples,min_samples=30)
    assert stats.sample_count == 3
    assert stats.actionable is False

def test_expectancy_is_average_realized_r():
    samples=[{"asset":"BTC","outcome":"WIN","realized_r":2.0},{"asset":"BTC","outcome":"LOSS","realized_r":-1.0}]
    stats=aggregate_samples(samples,min_samples=2)
    assert stats.expectancy_r == 0.5
    assert stats.win_rate == 0.5
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_e9_calibration.py -q`
Expected: FAIL because the calibration module does not exist.

- [ ] **Step 3: Implement isolated aggregation**

```python
def aggregate_samples(samples, min_samples=30):
    count=len(samples)
    wins=sum(s.get("outcome")=="WIN" for s in samples)
    rs=[float(s["realized_r"]) for s in samples if s.get("realized_r") is not None]
    return CalibrationStats(
        sample_count=count,
        win_rate=wins/count if count else 0.0,
        expectancy_r=sum(rs)/len(rs) if rs else 0.0,
        actionable=count >= min_samples,
    )
```

- [ ] **Step 4: Run tests and verify pass**

Run: `pytest tests/test_e9_calibration.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/e9_calibration.py tests/test_e9_calibration.py
git commit -m "feat: add asset-isolated E9 calibration statistics"
```

### Task 4: Persistent journal and E9 advisory calibration

**Files:**
- Modify: `production_v2/e9_learning.py`
- Modify: `production_v2/professional_brain.py`
- Test: `tests/test_e9_learning.py`

**Interfaces:**
- Produces `append_decision(path, record)`, `load_records(path)`, `build_advisory(record, stats)`.
- E9 receives calibration as `historical_context` and must label it advisory.

- [ ] **Step 1: Write the failing tests**

```python
def test_advisory_never_overrides_direction():
    stats={"actionable":True,"win_rate":0.9,"expectancy_r":1.2}
    a=build_advisory("BUY",stats)
    assert a["role"] == "ADVISORY"
    assert a["decision_override"] is False
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_e9_learning.py::test_advisory_never_overrides_direction -q`
Expected: FAIL until `build_advisory` exists.

- [ ] **Step 3: Implement append-only JSONL persistence and advisory context**

```python
def build_advisory(direction, stats):
    return {
        "role":"ADVISORY",
        "direction":direction,
        "sample_count":stats.get("sample_count",0),
        "win_rate":stats.get("win_rate",0.0),
        "expectancy_r":stats.get("expectancy_r",0.0),
        "actionable":bool(stats.get("actionable",False)),
        "decision_override":False,
    }
```

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_e9_learning.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add production_v2/e9_learning.py production_v2/professional_brain.py tests/test_e9_learning.py
git commit -m "feat: expose E9 historical calibration as advisory evidence"
```

### Task 5: Integration and regression verification

**Files:**
- Modify: `production_v2/pipeline.py`
- Modify: `production_v2/service.py` only if the existing service owns closed-candle persistence hooks.
- Test: `tests/test_e9_learning_integration.py`

**Interfaces:**
- Pipeline records every E9 decision once per closed candle.
- Outcome evaluator is invoked only when enough future candles exist.
- Existing NO_TRADE behavior remains valid.

- [ ] **Step 1: Write the failing integration tests**

```python
def test_pipeline_records_one_learning_sample_per_closed_candle():
    result=run_test_pipeline(asset="GOLD", candle_timestamp="2026-08-26T05:10:00Z")
    assert result.learning_sample_recorded is True
    assert run_test_pipeline(asset="GOLD", candle_timestamp="2026-08-26T05:10:00Z").learning_sample_recorded is False

def test_learning_does_not_enable_live_orders():
    result=run_test_pipeline(asset="BTC", candle_timestamp="2026-08-26T05:15:00Z")
    assert result.live_orders_allowed is False
```

- [ ] **Step 2: Run integration tests and verify failure**

Run: `pytest tests/test_e9_learning_integration.py -q`
Expected: FAIL until the pipeline hook exists.

- [ ] **Step 3: Add non-blocking learning hooks**

The pipeline must call the journal after E9, use a deterministic sample ID from asset+candle timestamp+E9 architecture version, and never use learning state to bypass E9 decision logic.

- [ ] **Step 4: Run the focused suite**

Run: `pytest tests/test_e9_learning.py tests/test_e9_calibration.py tests/test_e9_learning_integration.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full regression suite**

Run: `pytest -q`
Expected: PASS with no legacy engine being imported by `production_v2` runtime tests.

- [ ] **Step 6: Commit**

```bash
git add production_v2 tests
git commit -m "feat: integrate passive E9 replay learning"
```
