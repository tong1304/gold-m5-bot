# Professional Nine-Brain Opportunity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade E1–E9 so each brain can recognize profitable opportunity inside its own scope while preserving closed-candle, no-lookahead, evidence ownership, risk discipline, and E9 final authority.

**Architecture:** Keep the existing SINGLE_AXIS E1→E9 pipeline. Each brain emits domain evidence plus a distinct opportunity state/stage; opportunity visibility must never imply execution authorization. E9 remains the only final BUY/SELL authority and must fail closed.

**Tech Stack:** Python 3.14 runtime, Flask/Gunicorn, pandas/numpy/scipy, pytest, existing production_v2 contracts and opportunity layer.

**Spec:** Approved in chat on 2026-08-30: professional opportunity visibility with separate NO_OPPORTUNITY / OPPORTUNITY_WAITING / TRADE_READY semantics.

## Global Constraints

- Preserve E1→E2→E3→E4→E5→E6→E7→E8→E9 ordering.
- Preserve closed-candle-only and no-lookahead behavior.
- Preserve evidence ownership; downstream brains cannot rewrite upstream thesis.
- E9 remains the sole final BUY/SELL authority.
- Never loosen risk gates merely to increase signal frequency.
- Opportunity visibility and execution authorization must remain separate.
- Fail closed on missing data or E9 exceptions.

### Task 1: E1–E3 opportunity recognition

**Files:**
- Modify: `production_v2/e1_brain.py`
- Modify: `production_v2/e2_brain.py`
- Modify: `production_v2/e3_brain.py`

**Deliverable:** expose directional opportunity paths, maturity, counter-evidence, and next required events without authorizing trades.

- [ ] Add explicit opportunity lifecycle fields to each brain's final result.
- [ ] Ensure E2 does not label a directional opportunity unresolved when E1 directional evidence is internally convergent; represent missing auction proof separately.
- [ ] Ensure E3 distinguishes `STRUCTURE_FORMING`, `STRUCTURE_ESTABLISHED`, `STRUCTURE_BREAK`, and invalidation without using raw swing counts as authority.
- [ ] Preserve existing causal evidence and closed-candle rules.
- [ ] Run focused tests/import checks.

### Task 2: E4–E6 opportunity recognition

**Files:**
- Modify: `production_v2/e4_brain.py`
- Modify: `production_v2/e5_brain.py`
- Modify: `production_v2/e6_brain.py`

**Deliverable:** track auction lifecycle, location asymmetry, and setup lifecycle so a valid opportunity can remain visible while execution is blocked.

- [ ] Keep E4 candidate/confirmed/invalidated auction states distinct.
- [ ] Add opportunity direction and next-event semantics based on the current closed candle.
- [ ] Make E5 explicitly distinguish continuation opportunity from reversal opportunity and quantify directional space.
- [ ] Make E6 preserve a live setup thesis across validation stages while exposing exact proof gates.
- [ ] Run focused tests/import checks.

### Task 3: E7–E9 professional execution boundary

**Files:**
- Modify: `production_v2/e7_brain.py`
- Modify: `production_v2/e8_brain.py`
- Modify: `production_v2/e9_brain.py`
- Modify: `production_v2/opportunity_layer.py`
- Modify: `production_v2/pipeline.py`

**Deliverable:** convert confirmation/economics/master control into a professional decision boundary: opportunity can be visible before execution, but execution requires proof and viable geometry.

- [ ] E7 reports `WAITING_CONFIRMATION` with exact missing event rather than generic unresolved state.
- [ ] E8 separates economic opportunity from executable geometry; target/space/RR failures block execution without erasing the underlying opportunity.
- [ ] E9 synthesizes evidence, selects the strongest valid opportunity, and emits a deterministic final control state.
- [ ] Normalize opportunity states so `VISIBLE_PENDING_PROOF`, `VISIBLE_BUT_BLOCKED`, and `EXECUTABLE` are stable across all engines.
- [ ] Preserve E9 recovery/fail-closed behavior.
- [ ] Run the complete test suite and production import checks.

### Task 4: Verification

- [ ] Verify `python -m pytest -q`.
- [ ] Verify all nine `analyze_e*` imports.
- [ ] Verify pipeline returns `NO_TRADE` for the supplied BTC scenario without falsely declaring no opportunity.
- [ ] Verify an explicitly valid trade-plan fixture can reach E9 `EXECUTABLE` only when all proof/economic gates pass.
