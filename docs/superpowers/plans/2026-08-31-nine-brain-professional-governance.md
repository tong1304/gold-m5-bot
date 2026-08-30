# Nine-Brain Professional Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the E1→E9 production pipeline behave as one evidence-driven professional decision chain without allowing downstream brains to invent upstream evidence or bypass risk gates.

**Architecture:** Preserve the specialized responsibility of all nine existing brains and enforce a shared evidence/lifecycle contract at the pipeline boundary. E1 remains market-state authority, E2 opportunity mapping, E3 structure, E4 liquidity/auction, E5 location/value, E6 setup thesis, E7 confirmation, E8 trade economics, and E9 final market control. The pipeline adds deterministic normalization and hard veto propagation so contradictions become explicit rather than silently collapsing into generic UNRESOLVED output.

**Tech Stack:** Python 3, Flask/Gunicorn runtime, pytest, existing `production_v2` brain modules.

**Spec:** Approved nine-brain surgery plan in conversation; current production-v2 architecture and logs supplied by the user.

## Global Constraints

- Keep the execution order exactly `E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9`.
- E9 is the only engine allowed to authorize BUY/SELL.
- E1-E8 must never create final trade authority.
- Closed-candle evidence only; no lookahead.
- Scores remain descriptive and cannot override hard vetoes.
- A missing/contradictory upstream proof gate must propagate downstream as an explicit blocker.
- Do not increase signal frequency by weakening risk or confirmation thresholds.
- Preserve duplicate-candle protection and re-entry capability.
- GOLD requests with missing bars must remain a data error, not a synthetic market analysis.

---

### Task 1: Define the shared nine-brain evidence contract

**Files:**
- Create: `production_v2/professional_governance.py`
- Test: `production_v2/test_professional_governance.py`

**Interfaces:**
- Consumes: `dict[str, EngineResult]` from the existing pipeline.
- Produces: normalized evidence state with `hard_vetoes`, `missing_evidence`, `directional_conflicts`, `maturity`, and `next_required_event`.

- [ ] **Step 1: Write failing tests** covering: E1 trend-up + E3 transition conflict; E4 pending auction; E7 missing closed-candle confirmation; E8 invalid geometry; and a fully valid chain with no veto.
- [ ] **Step 2: Run `pytest production_v2/test_professional_governance.py -v` and verify the new tests fail before the implementation exists.
- [ ] **Step 3: Implement deterministic governance helpers that only read engine outputs, never mutate their ownership or manufacture evidence.
- [ ] **Step 4: Run the focused governance tests and verify they pass.
- [ ] **Step 5: Commit with `git add production_v2/professional_governance.py production_v2/test_professional_governance.py && git commit -m "feat: add nine-brain evidence governance"`.

### Task 2: Integrate governance into the single-axis pipeline

**Files:**
- Modify: `production_v2/pipeline.py`
- Test: `production_v2/test_single_brain_architecture.py`

**Interfaces:**
- Consumes: existing E1-E9 outputs and governance contract from Task 1.
- Produces: the same `DecisionResult` API, with strengthened `risk` metadata and final E9 reasons.

- [ ] **Step 1: Add a failing regression test asserting that a directional E1 result cannot authorize a trade while E3/E4/E7/E8 retain hard blockers.
- [ ] **Step 2: Run the focused regression test and verify it fails.
- [ ] **Step 3: Integrate governance immediately before final E9 authorization without changing engine order or individual brain ownership.
- [ ] **Step 4: Ensure `decision` remains `NO_TRADE` whenever governance emits any hard veto, even if an upstream output contains a BUY/SELL-shaped thesis.
- [ ] **Step 5: Run the full `production_v2` test suite with `pytest production_v2 -q` and verify all existing tests pass.
- [ ] **Step 6: Commit with `git add production_v2/pipeline.py production_v2/test_single_brain_architecture.py && git commit -m "feat: enforce nine-brain governance at pipeline boundary"`.

### Task 3: Improve production diagnostics for all nine engines

**Files:**
- Modify: `production_v2/pipeline.py`
- Test: `production_v2/test_single_brain_architecture.py`

**Interfaces:**
- Consumes: governance result from Task 2.
- Produces: per-cycle metadata showing each engine's maturity, vetoes, missing proof, and next required event.

- [ ] **Step 1: Add a regression assertion that the risk payload contains governance state for all nine engine IDs in `ENGINE_ORDER`.
- [ ] **Step 2: Run the regression and verify it fails.
- [ ] **Step 3: Add `professional_governance` and per-engine proof metadata to the existing `risk` dictionary without changing the public `DecisionResult` shape.
- [ ] **Step 4: Run the full test suite again and verify all tests pass.
- [ ] **Step 5: Commit with `git add production_v2/pipeline.py production_v2/test_single_brain_architecture.py && git commit -m "feat: expose nine-brain proof diagnostics"`.

### Task 4: Production verification against the supplied BTC log pattern

**Files:**
- Modify: `production_v2/test_professional_governance.py` only if regression coverage needs expansion.

**Interfaces:**
- Consumes: representative engine outputs matching the user's 16:58 BTC cycle.
- Produces: deterministic `NO_TRADE` governance with explicit blockers: structure unresolved, auction pending, confirmation missing, and trade geometry/risk invalid.

- [ ] **Step 1: Encode the supplied 16:58 evidence pattern as a fixture using only the logged values and states.
- [ ] **Step 2: Run the fixture test and verify the governance result is `NO_TRADE`.
- [ ] **Step 3: Verify no rule invents an auction confirmation, structural break, target, or probability edge.
- [ ] **Step 4: Run `pytest production_v2 -q` as the final verification.
- [ ] **Step 5: Commit the final regression fixture with `git add production_v2/test_professional_governance.py && git commit -m "test: lock nine-brain no-trade regression"`.
