# Opportunity Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Production V2 discover and preserve profitable directional opportunities before confirmation and risk gates, while keeping execution conservative.

**Architecture:** Add an Opportunity Book between opportunity discovery and thesis construction. E2 produces directional conditional candidates; the book preserves competing BUY/SELL candidates and causal lineage; E6 consumes the book to form a setup thesis; E7/E8/E9 remain confirmation, economics, and governance boundaries.

**Tech Stack:** Python 3, existing `production_v2` modules, pytest, Postgres-backed opportunity memory, existing GitHub Actions/Render runtime.

**Spec:** `docs/superpowers/specs/2026-09-06-opportunity-intelligence-design.md`

## Global Constraints

- Closed M5 candles remain the authoritative evaluation clock.
- Do not lower existing risk/quality thresholds to increase signal count.
- E7 cannot create a thesis.
- E8 cannot create an opportunity.
- E9 cannot manufacture an opportunity.
- Existing E4/E6 surgery and lifecycle semantics must remain intact.
- Same-candle processing must remain idempotent.
- BUY and SELL candidates may coexist conditionally.
- Opportunity quality must remain distinct from entry-now economics.

---

### Task 1: Add the Opportunity Book core

**Files:**
- Create: `production_v2/opportunity_book.py`
- Test: `production_v2/test_opportunity_book.py`

**Interfaces:**
- Consumes: normalized engine evidence dictionaries and the current closed-candle identifier.
- Produces: `OpportunityCandidate`, `build_candidate()`, `update_book()`, `compare_candidates()`.

- [ ] **Step 1: Write failing tests for independent BUY/SELL candidates**

```python
def test_book_keeps_competing_directional_candidates():
    book = update_book({}, [
        build_candidate("BUY", "TREND_CONTINUATION", "2026-09-06T12:50:00Z", quality=0.78),
        build_candidate("SELL", "SWEEP_REJECTION", "2026-09-06T12:50:00Z", quality=0.62),
    ])
    assert {x["direction"] for x in book["candidates"]} == {"BUY", "SELL"}
    assert book["leader"] == "BUY"
    assert book["competition"] == "CONTESTED"
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python -m pytest -q production_v2/test_opportunity_book.py`
Expected: FAIL because `production_v2.opportunity_book` does not yet expose the required interfaces.

- [ ] **Step 3: Implement the minimal typed candidate/book model**

```python
VALID_DIRECTIONS = {"BUY", "SELL"}
TERMINAL = {"INVALIDATED", "EXPIRED", "REPLACED", "EXECUTED"}

def build_candidate(direction, family, origin_candle, quality=0.0, **evidence):
    direction = str(direction).upper().strip()
    if direction not in VALID_DIRECTIONS:
        raise ValueError("direction must be BUY or SELL")
    return {
        "direction": direction,
        "family": str(family).upper().strip(),
        "origin_candle": origin_candle,
        "quality": max(0.0, min(1.0, float(quality))),
        "state": "FORMING",
        "wait_for": list(evidence.get("wait_for") or []),
        "causal_evidence": dict(evidence.get("causal_evidence") or {}),
        "invalidation_conditions": list(evidence.get("invalidation_conditions") or []),
    }

def compare_candidates(candidates):
    active = [c for c in candidates if c.get("state") not in TERMINAL]
    ranked = sorted(active, key=lambda c: float(c.get("quality", 0.0)), reverse=True)
    directions = {c.get("direction") for c in active}
    return {
        "leader": ranked[0]["direction"] if ranked else "NEUTRAL",
        "competition": "CONTESTED" if directions == {"BUY", "SELL"} else "UNCONTESTED",
        "ranked": ranked,
    }

def update_book(previous, candidates):
    merged = list(previous.get("candidates") or [])
    for candidate in candidates:
        merged = [x for x in merged if not (x.get("direction") == candidate.get("direction") and x.get("family") == candidate.get("family"))]
        merged.append(candidate)
    comparison = compare_candidates(merged)
    return {"candidates": merged, **comparison}
```

- [ ] **Step 4: Add tests for lifecycle preservation, invalidation, and idempotency**

```python
def test_same_candle_does_not_duplicate_candidate():
    candidate = build_candidate("BUY", "TREND_CONTINUATION", "C1")
    once = update_book({}, [candidate])
    twice = update_book(once, [candidate])
    assert len(twice["candidates"]) == 1

def test_poor_entry_does_not_invalidate_opportunity():
    candidate = build_candidate("BUY", "TREND_CONTINUATION", "C1", quality=0.8, wait_for=["PULLBACK"])
    assert candidate["state"] == "FORMING"
    assert candidate["wait_for"] == ["PULLBACK"]
```

- [ ] **Step 5: Run the focused tests**

Run: `python -m pytest -q production_v2/test_opportunity_book.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/opportunity_book.py production_v2/test_opportunity_book.py
git commit -m "feat: add directional opportunity book"
```

---

### Task 2: Make E2 an opportunity hunter without making it an execution brain

**Files:**
- Modify: `production_v2/e2_brain.py`
- Test: `production_v2/test_e2_opportunity_hunter.py`

**Interfaces:**
- Consumes: E1 context plus current market evidence.
- Produces: `opportunity_candidates` containing conditional BUY/SELL candidates and explicit `wait_for` conditions.

- [ ] **Step 1: Write failing tests for conditional opportunities**

```python
def test_e2_can_preserve_contextual_buy_while_sell_event_is_pending():
    output = analyze_e2({
        "e1": {"market_state": "TREND_UP", "direction": "BUY"},
        "e4": {"direction": "SELL", "state": "PENDING"},
    })
    directions = {x["direction"] for x in output["opportunity_candidates"]}
    assert "BUY" in directions
    assert "SELL" in directions
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest -q production_v2/test_e2_opportunity_hunter.py`
Expected: FAIL because the current E2 contract does not expose the candidate list.

- [ ] **Step 3: Implement candidate discovery using existing E2 evidence**

```python
candidates = []
if bullish_context and continuation_conditions:
    candidates.append({
        "direction": "BUY",
        "family": "TREND_CONTINUATION",
        "state": "DEVELOPING",
        "wait_for": buy_wait_for,
        "causal_evidence": buy_evidence,
    })
if bearish_event and bearish_event_is_causal:
    candidates.append({
        "direction": "SELL",
        "family": "LIQUIDITY_REVERSAL",
        "state": "FORMING",
        "wait_for": sell_wait_for,
        "causal_evidence": sell_evidence,
    })
output["opportunity_candidates"] = candidates
```

The implementation must retain existing E2 findings/reason codes and must not emit `TRADE` or execution authorization.

- [ ] **Step 4: Add tests that prevent E2 from collapsing to latest-event direction**

```python
def test_e2_does_not_replace_buy_context_with_latest_sell_event():
    output = analyze_e2({
        "e1": {"market_state": "TREND_UP", "direction": "BUY"},
        "e4": {"direction": "SELL", "state": "PENDING"},
    })
    assert any(x["direction"] == "BUY" for x in output["opportunity_candidates"])
```

- [ ] **Step 5: Run E2 tests**

Run: `python -m pytest -q production_v2/test_e2_opportunity_hunter.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/e2_brain.py production_v2/test_e2_opportunity_hunter.py
git commit -m "feat: make E2 preserve conditional opportunities"
```

---

### Task 3: Connect the Opportunity Book to E6 while preserving existing lifecycle authority

**Files:**
- Modify: `production_v2/e6_brain.py`
- Modify: `production_v2/opportunity_lifecycle.py`
- Modify: `production_v2/pipeline.py`
- Test: `production_v2/test_opportunity_pipeline.py`

**Interfaces:**
- Consumes: E2 `opportunity_candidates`, E3/E4/E5 evidence, persisted Opportunity Book, and existing E6 surgery output.
- Produces: E6 thesis/watch semantics plus a book snapshot attached to pipeline output.

- [ ] **Step 1: Write failing integration tests**

```python
def test_pipeline_preserves_buy_and_sell_opportunities_before_thesis_resolution():
    result = run_fixture_pipeline("BTC", "2026-09-06T12:50:00Z")
    book = result["opportunity_book"]
    assert {x["direction"] for x in book["candidates"]} >= {"BUY", "SELL"}
    assert result["E6"]["setup"] in {"OPPORTUNITY_WATCH", "UNKNOWN"} or result["E6"].get("setup")

def test_e6_watch_does_not_promote_to_setup_without_thesis_proof():
    result = run_fixture_pipeline("BTC", "C1", thesis_proven=False)
    assert result["E6"].get("e6_thesis_proven") is not True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest -q production_v2/test_opportunity_pipeline.py`
Expected: FAIL because the pipeline does not yet carry the Opportunity Book contract.

- [ ] **Step 3: Wire E2 candidates into the book before E6**

```python
e2_output = results["E2"].output
candidates = e2_output.get("opportunity_candidates") or []
book = opportunity_book.update_book(previous_book, candidates)
results["E2"] = _with_output(results["E2"], {"opportunity_book_snapshot": book})
results["E6"] = _with_output(results["E6"], {"opportunity_book_snapshot": book})
```

E6 must select/maintain a causal candidate only when its existing evidence rules prove a setup thesis. If no thesis is proven, it remains `OPPORTUNITY_WATCH`/watch-only.

- [ ] **Step 4: Preserve the existing lifecycle regression behavior**

```python
def test_pending_watch_remains_watch_without_thesis_proof():
    current = {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "candidate": True,
        "thesis_proven": False,
        "upstream_evidence": True,
    }
    state = advance_opportunity(previous_watch_state(), current)
    assert state["state"] == "WATCHING"
```

- [ ] **Step 5: Run all opportunity/lifecycle tests**

Run: `python -m pytest -q production_v2/test_opportunity_book.py production_v2/test_opportunity_pipeline.py production_v2/test_opportunity_lifecycle.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/e6_brain.py production_v2/opportunity_lifecycle.py production_v2/pipeline.py production_v2/test_opportunity_pipeline.py
git commit -m "feat: connect opportunity book to thesis lifecycle"
```

---

### Task 4: Separate opportunity quality from entry-now economics

**Files:**
- Modify: `production_v2/e5_brain.py`
- Modify: `production_v2/e8_brain.py`
- Modify: `production_v2/profit_edge.py`
- Test: `production_v2/test_opportunity_economics.py`

**Interfaces:**
- Consumes: location/value evidence, surviving E6 thesis, trade plan, and historical outcomes.
- Produces: `opportunity_quality`, `entry_now_quality`, `wait_conditions`, and existing economic evidence without deleting a valid opportunity.

- [ ] **Step 1: Write failing test for high-quality opportunity with poor current entry**

```python
def test_high_opportunity_quality_can_have_poor_entry_now_quality():
    result = evaluate_fixture_economics(
        opportunity_quality=0.82,
        location_quality=0.42,
        rr=1.1,
    )
    assert result["opportunity_quality"] >= 0.8
    assert result["entry_now_quality"] < 0.5
    assert result["state"] == "WAIT_FOR_LOCATION"
```

- [ ] **Step 2: Run focused test and verify failure**

Run: `python -m pytest -q production_v2/test_opportunity_economics.py`
Expected: FAIL because the current economics contract does not expose the two independent quality dimensions.

- [ ] **Step 3: Add non-destructive economics fields**

```python
out["opportunity_quality"] = float(opportunity_quality)
out["entry_now_quality"] = float(entry_now_quality)
out["wait_conditions"] = list(wait_conditions)
if opportunity_quality >= 0.70 and entry_now_quality < 0.50:
    out["economic_state"] = "WAIT_FOR_LOCATION"
```

Existing E8 risk blocks remain authoritative for execution. This task must not relax RR, stop, probability, cost, or risk limits.

- [ ] **Step 4: Add tests proving E8 still blocks unsafe economics**

```python
def test_poor_rr_still_blocks_execution_even_when_opportunity_is_high():
    result = evaluate_fixture_economics(opportunity_quality=0.90, rr=0.8)
    assert result["trade_authorized"] is not True
```

- [ ] **Step 5: Run economics regression tests**

Run: `python -m pytest -q production_v2/test_opportunity_economics.py production_v2/test_e8_trade_economics.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add production_v2/e5_brain.py production_v2/e8_brain.py production_v2/profit_edge.py production_v2/test_opportunity_economics.py
git commit -m "feat: separate opportunity quality from entry economics"
```

---

### Task 5: Add missed-opportunity measurement and full regression verification

**Files:**
- Modify: `production_v2/opportunity_memory.py`
- Modify: `production_v2/pipeline.py`
- Test: `production_v2/test_missed_opportunity.py`

**Interfaces:**
- Consumes: persisted opportunity candidates and subsequent closed-candle outcomes.
- Produces: terminal opportunity outcomes `CONFIRMED_WINNER`, `CONFIRMED_LOSER`, `INVALIDATED`, `EXPIRED`, `MISSED_EXECUTION` and aggregate recall/false-opportunity statistics.

- [ ] **Step 1: Write failing outcome tests**

```python
def test_opportunity_that_reaches_target_without_execution_is_marked_missed():
    outcome = classify_opportunity_outcome(
        candidate={"direction": "BUY", "state": "TRIGGER_PENDING"},
        path={"mfe_r": 2.1, "trade_executed": False},
    )
    assert outcome == "MISSED_EXECUTION"

def test_invalidated_opportunity_is_not_counted_as_missed_winner():
    outcome = classify_opportunity_outcome(
        candidate={"direction": "BUY", "state": "INVALIDATED"},
        path={"mfe_r": 0.2, "trade_executed": False},
    )
    assert outcome == "INVALIDATED"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest -q production_v2/test_missed_opportunity.py`
Expected: FAIL because outcome classification is not yet available.

- [ ] **Step 3: Implement outcome classification and persisted counters**

```python
def classify_opportunity_outcome(candidate, path):
    state = str(candidate.get("state") or "").upper()
    if state == "INVALIDATED":
        return "INVALIDATED"
    if state == "EXPIRED":
        return "EXPIRED"
    if path.get("trade_executed"):
        return "CONFIRMED_WINNER" if float(path.get("net_r", 0.0)) > 0 else "CONFIRMED_LOSER"
    if state in {"TRIGGER_PENDING", "EXECUTABLE"} and float(path.get("mfe_r", 0.0)) >= 1.0:
        return "MISSED_EXECUTION"
    return "OPEN"
```

- [ ] **Step 4: Run complete production_v2 test suite**

Run: `python -m pytest -q production_v2`
Expected: PASS with zero regressions.

- [ ] **Step 5: Verify imports and production entry point**

Run: `python -m py_compile production_v2/*.py`
Expected: exit code 0 with no syntax errors.

- [ ] **Step 6: Verify branch status and CI**

Run: `git status --short` and the repository's existing GitHub Actions test workflow.
Expected: clean working tree after commits and a successful CI run for the final commit.

- [ ] **Step 7: Commit**

```bash
git add production_v2/opportunity_memory.py production_v2/pipeline.py production_v2/test_missed_opportunity.py
git commit -m "feat: measure missed opportunities"
```

## Final Verification Checklist

- [ ] BUY and SELL opportunities can coexist.
- [ ] Latest liquidity event cannot erase an older causal opportunity by itself.
- [ ] Conditional opportunities survive across closed candles.
- [ ] Poor entry economics produce WAIT rather than deletion of opportunity quality.
- [ ] E6 remains thesis authority.
- [ ] E7 remains trigger authority only.
- [ ] E8 remains economics/risk authority only.
- [ ] E9 remains final governance authority only.
- [ ] Existing lifecycle regression tests pass.
- [ ] Same-candle idempotency passes.
- [ ] Full production_v2 tests pass.
- [ ] Python compilation passes.
- [ ] CI passes before claiming the surgery is production-ready.
