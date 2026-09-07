# Professional Opportunity Lifecycle Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Production V2 from a rigid all-gates-at-once evaluator into a causal opportunity lifecycle while preserving strict E9 execution governance.

**Architecture:** Add a small lifecycle/economics controller around the existing E1-E9 pipeline. Keep specialist engines intact where possible; make E4 the event-clock anchor, E6 the thesis owner, E7 setup-aware confirmer, E8 pre/final economics, and E9 the only execution authority.

**Tech Stack:** Python 3, existing `EngineResult`/`DecisionResult`, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-07-professional-opportunity-lifecycle.md`

## Global Constraints
- Closed M5 candles only; no lookahead.
- E9 remains the sole execution authority.
- Do not lower thresholds merely to create more trades.
- Structural space blocks tradeability/economics, not opportunity detection.
- Preserve existing E1-E5 factual evidence and E9 governance semantics.

---

### Task 1: Lock regression tests for causal direction, lifecycle, and canonical clock
**Files:**
- Create: `production_v2/test_professional_opportunity_lifecycle.py`

- [ ] Write tests proving a LOW_SWEEP_REJECTION can create a BUY opportunity even when E1 pressure is bearish.
- [ ] Write tests proving WATCH can advance to THESIS_FORMED/ARMED without execution authorization.
- [ ] Write tests proving event age is derived from one canonical event candle.
- [ ] Write tests proving structural space marks tradeability poor without deleting the opportunity.
- [ ] Run targeted tests in CI or local environment; verify they fail before implementation.

### Task 2: Make E6 event-causal direction authoritative and separate opportunity from economics
**Files:**
- Modify: `production_v2/e6_brain.py`

- [ ] Write/extend tests for event-direction priority.
- [ ] Change causal direction ordering to prefer E4 directional event, then E2, with E1/E3 treated as context/counter-evidence.
- [ ] Keep E6 invalidation strict.
- [ ] Remove structural-space-as-opportunity-killer behavior; expose `tradeability=CONSTRAINED` instead.
- [ ] Run E6 regression suite.

### Task 3: Add explicit professional lifecycle controller
**Files:**
- Create: `production_v2/professional_opportunity_controller.py`
- Modify: `production_v2/pipeline.py`

- [ ] Implement states `NO_OPPORTUNITY`, `DETECTED`, `WATCH`, `THESIS_FORMED`, `ARMED`, `CONFIRMED`, `EXECUTE`, `MANAGE`, plus invalidated/expired/superseded outcomes.
- [ ] Preserve opportunity identity across candles using the E4 causal event id.
- [ ] Compute canonical event age once and attach it to every downstream state.
- [ ] Promote to ARMED only when thesis is proven and E8 pre-economics are acceptable; never authorize execution at ARMED.
- [ ] Keep E9 as the final execution gate.
- [ ] Run lifecycle regression tests.

### Task 4: Add E8 pre-economic analysis and final economic separation
**Files:**
- Create: `production_v2/e8_precheck.py`
- Modify: `production_v2/pipeline.py`

- [ ] Add precheck fields for direction, ATR, structural space, estimated risk, target space, estimated RR, and execution-cost stress.
- [ ] Allow E8-PRE to operate when E6 is a surviving opportunity thesis even if E7 has not confirmed entry.
- [ ] Keep E8-FINAL as the final economics gate after E7 confirmation.
- [ ] Run economics tests.

### Task 5: Canonicalize Telegram output
**Files:**
- Modify: `production_v2/notifications/no_trade.py`
- Create: `production_v2/notifications/opportunity_snapshot.py`

- [ ] Render WATCH/ARMED/CONFIRMED from the same E9 lifecycle snapshot.
- [ ] Include candle id, causal event id, canonical event age, thesis state, confirmation state, economics state, and execution authorization.
- [ ] Prevent stale/mixed snapshots from being formatted as the current decision.
- [ ] Run notification tests.

### Task 6: Full regression and deployment verification
**Files:**
- Modify only if tests reveal integration defects.

- [ ] Run all `production_v2` tests.
- [ ] Run replay/backtest checks for XAUUSD and BTC M5.
- [ ] Verify E4/E6/E7/E8/E9 and Telegram report the same candle/event snapshot.
- [ ] Verify no execution is authorized from WATCH or ARMED.
- [ ] Verify Render/GitHub Actions deployment succeeds before considering the branch release-ready.
