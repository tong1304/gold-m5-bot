# Opportunity Lifecycle V10 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Repair the E4→E6 pending-opportunity handoff, cross-candle opportunity persistence/reconciliation, and downstream confirmation/economics boundaries without weakening E7/E8/E9 trade governance.

**Architecture:** Keep E1–E5 evidence production unchanged unless a failing regression proves an interface defect. E6 remains the sole setup/thesis owner and may emit an explicit non-trade `OPPORTUNITY_WATCH`; the lifecycle persists and reconciles that watch across closed M5 candles. E7 confirms only an E6 thesis, E8 evaluates only a valid setup/confirmation, and E9 remains final authority.

**Tech Stack:** Python, pytest, Flask/Gunicorn runtime, PostgreSQL opportunity memory, existing Production V2 E1–E9 contracts.

**Spec:** Approved in chat on 2026-09-06; diagnosis based on production-v2 runtime logs and current pipeline/E6/E7 implementation.

## Global Constraints

- Closed-candle evidence only; no lookahead and no open-candle borrowing.
- E6 is the authoritative opportunity/setup owner; E7 never creates a thesis.
- Pending opportunity watch is never trade permission.
- Do not lower E7/E8/E9 safety gates to increase order count.
- Preserve duplicate-candle protection and PostgreSQL persistence.
- Do not modify E1–E5 strategy semantics except to fix a proven contract/handoff defect.

### Task 1: Reproduce the E4→E6 regression

**Files:**
- Test: `production_v2/tests/` existing test location discovered from repository
- Inspect: `production_v2/e6_pending_event_surgery.py`
- Inspect: `production_v2/pipeline.py`

**Interfaces:**
- Input: E1–E5 `EngineResult` outputs representing the 2026-09-06 pending LOW_ACCEPTANCE_CANDIDATE case.
- Expected: E6 returns `OPPORTUNITY_WATCH`/forming or contested watch, never `NO_CAUSAL_OPPORTUNITY`, when the pending event is valid and not invalidated.

- [ ] Add a focused failing regression test.
- [ ] Run only that test and verify it fails for the diagnosed reason.

### Task 2: Repair E6 runtime handoff

**Files:**
- Modify: `production_v2/e6_pending_event_surgery.py`
- Modify only if required: `production_v2/pipeline.py`
- Test: regression test from Task 1

**Interfaces:**
- `patched_analyze_e6(snapshot, upstream)` must consume the actual pipeline E4/E5 results and preserve the pending-event candidate identity.
- Output must explicitly include `setup=OPPORTUNITY_WATCH`, `candidate_type=OPPORTUNITY_CANDIDATE`, `watch_only=True`, `trade_ready=False`, `e6_thesis_proven=False`, event/opportunity identity, and missing proof.

- [ ] Implement the smallest fix that makes Task 1 green.
- [ ] Add a test proving no trade permission is created by a watch.
- [ ] Run focused E6 tests.

### Task 3: Repair lifecycle persistence and reconciliation

**Files:**
- Modify: `production_v2/pipeline.py`
- Inspect/modify only if required: opportunity-memory module used by pipeline
- Test: lifecycle/persistence tests

**Interfaces:**
- `advance_opportunity`/`_lifecycle_current` must preserve a valid watch across the next closed candle.
- Current-candle evidence may update, confirm, replace, or invalidate the watch, but `NO_SETUP` from a downstream confirmation stage must not silently erase a still-valid persisted opportunity.

- [ ] Add failing persistence/reconciliation tests.
- [ ] Verify failure.
- [ ] Implement minimal reconciliation fix.
- [ ] Run lifecycle tests.

### Task 4: Verify E7/E8 boundaries

**Files:**
- Inspect: `production_v2/e7_brain.py`
- Inspect: `production_v2/e8_brain.py`
- Test: boundary/regression tests

**Interfaces:**
- E7 must remain `NO_SURVIVING_SETUP` when E6 has no thesis.
- E7 may evaluate a watch only when E6 exposes the appropriate thesis/confirmation contract.
- E8 must remain `NOT_APPLICABLE` when E6 thesis/required setup is absent.
- Insufficient structural space remains a downstream blocker, not a reason to create a trade.

- [ ] Add regression tests for E7 no-thesis and E8 no-thesis cases.
- [ ] Run them and ensure current safety behavior remains green.

### Task 5: Verify E9 final authority and duplicate handling

**Files:**
- Inspect: `production_v2/pipeline.py`
- Inspect: `production_v2/e9_brain.py`
- Test: end-to-end pipeline tests

- [ ] Add/adjust tests proving E9 veto cannot be bypassed.
- [ ] Add/adjust duplicate-candle regression test.
- [ ] Run end-to-end tests.

### Task 6: Runtime diagnostics

**Files:**
- Modify only if needed: `production_v2/app.py`, `production_v2/pipeline.py`, or E6 surgery

- [ ] Emit an unambiguous E6 binding/call-path diagnostic including module, function, version, input event state, and output lifecycle state.
- [ ] Ensure diagnostics do not leak secrets.
- [ ] Run tests.

### Task 7: Full verification

**Files:**
- No production changes unless a failing test exposes a defect.

- [ ] Run the complete available pytest suite.
- [ ] Run focused regression suite again.
- [ ] Perform syntax/import checks.
- [ ] Review git diff for unintended E1–E5 strategy changes.
- [ ] Deploy only after verification is green.
- [ ] Validate Render startup and one closed-candle evaluation after deployment.
