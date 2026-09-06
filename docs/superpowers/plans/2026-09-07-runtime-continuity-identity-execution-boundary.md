# Runtime Continuity Identity Execution Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Production V2 preserve opportunities across closed M5 candles, keep causal event identity separate from opportunity identity, and model broker execution explicitly without weakening E9.

**Architecture:** Keep lifecycle progression in `opportunity_lifecycle_progression.py`; make the surgery wrapper responsible for assembling/persisting identity and runtime audit fields; add a small execution-boundary state machine that accepts an E9-authorized intent but never claims broker execution without an external acknowledgement. Tests cover each boundary independently and an end-to-end multi-candle progression fixture.

**Tech Stack:** Python 3, pytest, existing `DecisionResult`/`EngineResult`, PostgreSQL-backed `opportunity_memory`.

**Spec:** `docs/superpowers/specs/2026-09-07-runtime-continuity-identity-execution-boundary-design.md`

## Global Constraints
- E9 remains the sole final trade authority.
- Do not change thresholds, scores, RR requirements, pattern/trigger quality, or E9 decision criteria.
- Advance at most one lifecycle stage per closed candle.
- Preserve `opportunity_id` and `origin_event_id` for a surviving opportunity.
- Allow `event_id` to advance without changing opportunity identity.
- `ORDER_INTENT` is not broker execution.

---

### Task 1: Lock identity continuity with failing tests

**Files:**
- Modify: `production_v2/test_opportunity_lifecycle_progression.py`
- Test: `production_v2/test_opportunity_lifecycle_progression.py`

**Interfaces:**
- Consumes: `advance_lifecycle_stage`.
- Produces: executable regression coverage for multi-candle identity continuity.

- [ ] Step 1: Add a test where WATCH on event A is followed by CONFIRMED on event B and assert the same `opportunity_id` and immutable `origin_event_id`.
- [ ] Step 2: Run the focused test and verify it fails against the current behavior if identity is not preserved correctly.
- [ ] Step 3: Add tests for terminal same-event blocking and genuinely-new-event restart.
- [ ] Step 4: Run the focused lifecycle tests.

### Task 2: Implement identity/runtime audit fields

**Files:**
- Modify: `production_v2/opportunity_lifecycle_progression.py`
- Modify: `production_v2/opportunity_lifecycle_progression_surgery.py`

**Interfaces:**
- Consumes: current E4 event, prior lifecycle, closed-candle timestamp.
- Produces: stable `opportunity_id`, immutable `origin_event_id`, current `event_id`, `last_progression_candle`, and auditable stage history.

- [ ] Step 1: Implement the minimum identity preservation needed by the failing tests.
- [ ] Step 2: Ensure new-event detection resets only terminal opportunities, not active opportunities.
- [ ] Step 3: Persist symbol and audit fields in the direction-specific lifecycle item and top-level lifecycle.
- [ ] Step 4: Run lifecycle and surgery-focused tests.

### Task 3: Add execution boundary state machine with failing tests

**Files:**
- Create: `production_v2/order_execution_boundary.py`
- Create: `production_v2/test_order_execution_boundary.py`

**Interfaces:**
- Consumes: E9 decision/gate and lifecycle execution intent.
- Produces: `NONE`, `ORDER_INTENT`, `ORDER_SUBMITTED`, `BROKER_ACCEPTED`, `POSITION_OPEN`, plus explicit rejection/failure states.

- [ ] Step 1: Write tests proving non-E9/non-gated input cannot create ORDER_INTENT.
- [ ] Step 2: Write tests proving ORDER_INTENT cannot become POSITION_OPEN without explicit external acknowledgements.
- [ ] Step 3: Run the focused tests and verify RED.
- [ ] Step 4: Implement the minimal pure state transition functions.
- [ ] Step 5: Run the focused execution-boundary tests and verify GREEN.

### Task 4: Bind execution boundary without overriding E9

**Files:**
- Modify: `production_v2/opportunity_lifecycle_progression_surgery.py`
- Modify: `production_v2/app.py` if startup binding is required

**Interfaces:**
- Consumes: progressed lifecycle and final E9 decision.
- Produces: explicit execution-boundary state; no broker-success inference.

- [ ] Step 1: Add a regression test that a TRADE lifecycle yields ORDER_INTENT only when E9 is gated and decisive.
- [ ] Step 2: Bind the execution state to lifecycle/risk output.
- [ ] Step 3: Keep existing terminal lifecycle conversion to NO_TRADE.
- [ ] Step 4: Add startup telemetry identifying the execution boundary.
- [ ] Step 5: Run all focused tests.

### Task 5: Full regression and verification

**Files:**
- Modify: existing tests only if regressions require precise assertions.

- [ ] Step 1: Run the full Production V2 pytest suite in an environment with repository dependencies.
- [ ] Step 2: Inspect git diff for forbidden threshold/E9 changes.
- [ ] Step 3: Check GitHub Actions status for the resulting commit.
- [ ] Step 4: Verify deployment logs show stable identity fields across consecutive closed candles.
- [ ] Step 5: Report any environment-limited verification honestly; do not claim broker execution unless externally acknowledged.
