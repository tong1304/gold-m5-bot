# E9 Final Governance Rebalance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebalance E9 so it authorizes a trade when E6 Core Thesis, E7 valid closed-candle Trigger, and E8 Survivable Economics are satisfied, while treating non-fatal E1–E5 evidence as supporting conviction rather than universal hard vetoes.

**Architecture:** E6 owns the trade thesis, E7 owns trigger/confirmation, E8 owns trade economics, and E9 owns final authorization. E1–E5 remain authoritative evidence providers but their unresolved or pending states are not automatically fatal unless they expose a true thesis invalidation, structural impossibility, or fatal execution/economic conflict.

**Tech Stack:** Python, existing `EngineResult` contract, pytest, GitHub Actions.

**Spec:** This plan supersedes the overly strict interpretation of the existing E9 four-layer governance contract for the execution decision while preserving data-integrity and fatal-risk protections.

## Global Constraints

- Closed M5 candle evidence only; no lookahead.
- E6 remains the sole owner of Core Thesis.
- E7 remains the sole owner of valid closed-candle Trigger/Confirmation.
- E8 remains the sole owner of Survivable Economics/Risk.
- E9 is the sole owner of final authorization.
- E9 must not manufacture or rewrite upstream facts.
- Pending supporting evidence is not a fatal veto by itself.
- Fatal invalidation, invalid trade geometry, unusable structural risk, or execution-policy failure remains a hard veto.
- Preserve WATCH as a distinct state from NO_TRADE.
- Do not lower thresholds merely to increase signal count.

---

### Task 1: Define the E9 decision contract in regression tests

**Files:**
- Create: `tests/test_e9_final_governance_rebalance.py`
- Modify: `production_v2/e9_brain.py` only after tests are written

**Interfaces:**
- Consumes: `analyze_e9(snapshot, upstream)` and existing `EngineResult` outputs.
- Produces: explicit assertions for `EXECUTE`, `WATCH`, and `NO_TRADE` semantics.

- [ ] **Step 1: Write failing tests**
  - Core thesis + valid trigger + survivable economics must be eligible for `BUY`/`SELL` even when one or more non-fatal E1–E5 evidence states are pending.
  - Core thesis without trigger must produce `WATCH`, not execution.
  - Core thesis + trigger with fatal economics must produce `NO_TRADE`.
  - Thesis invalidation must produce `NO_TRADE`.
  - E9 must report E6/E7/E8 ownership explicitly.
  - E9 must not bypass E7 or E8.

- [ ] **Step 2: Run focused tests and confirm they fail against the current policy**

Run: `pytest tests/test_e9_final_governance_rebalance.py -q`

Expected: failures demonstrating that unresolved supporting evidence / current hard-gate semantics are too restrictive.

### Task 2: Implement the E9 authority rebalance

**Files:**
- Modify: `production_v2/e9_brain.py`

**Interfaces:**
- Consumes: E1–E8 evidence already passed through the pipeline.
- Produces: final E9 output with explicit `decision`, `governance_decision`, `execution_state`, `watch_state`, `supporting_evidence`, `fatal_conflicts`, and `proof_summary`.

- [ ] **Step 1: Separate evidence classes**
  - `SUPPORTING`: E1–E5 alignment, pending auction confirmation, directional context weakness, non-fatal location concerns.
  - `MANDATORY`: E6 thesis, E7 trigger, E8 survivable economics.
  - `FATAL`: thesis invalidation, invalid structural risk, invalid trade geometry, unacceptable execution conditions, explicit E7/E8 invalidation.

- [ ] **Step 2: Make lifecycle explicit**
  - `NO_THESIS` when E6 has no surviving thesis.
  - `WATCH` when E6 thesis survives but E7 trigger is missing, or E8 is not yet evaluable and no fatal failure exists.
  - `EXECUTABLE` only when E6 thesis + E7 valid trigger + E8 survivable economics are all proven and no fatal veto exists.
  - `NO_TRADE` for fatal invalidation/economics/execution failures.

- [ ] **Step 3: Preserve conviction information**
  - Include supporting evidence quality and counter-evidence in E9 output.
  - Do not convert supporting evidence into a mandatory all-pass gate.
  - Preserve explicit reason codes explaining why conviction is reduced.

- [ ] **Step 4: Preserve hard protections**
  - Data integrity failure remains fatal.
  - Thesis invalidation remains fatal.
  - Invalid SL/target geometry, insufficient survivable space, or failed execution policy remains fatal.
  - E9 cannot create a trigger or thesis that E6/E7 did not provide.

### Task 3: Verify pipeline and lifecycle integration

**Files:**
- Modify: `production_v2/pipeline.py` only if required by the new E9 output contract.
- Modify: `production_v2/professional_opportunity.py` only if required to map E9 WATCH/EXECUTABLE semantics correctly.

- [ ] **Step 1: Run focused E9 tests**
- [ ] **Step 2: Run existing E9/professional-opportunity regressions**
- [ ] **Step 3: Run the complete production-v2 pytest suite**
- [ ] **Step 4: Verify no regression in E3 public-contract tests**

### Task 4: Validate with replay/runtime evidence

- [ ] Confirm a developing opportunity remains `WATCH` while trigger proof is missing.
- [ ] Confirm a qualified thesis with a valid trigger and survivable economics can reach `EXECUTABLE` despite non-fatal supporting evidence being imperfect.
- [ ] Confirm fatal conflicts still force `NO_TRADE`.
- [ ] Confirm duplicate candles remain skipped.
- [ ] Confirm no lookahead appears in E9 output.
- [ ] Compare signal frequency and outcome quality before/after; do not accept an increase in trades without evidence that trade quality remains acceptable.

### Task 5: Final verification gate

- [ ] GitHub Actions is green for the new E9 regression tests.
- [ ] Full test suite is green.
- [ ] Production deployment starts successfully.
- [ ] Runtime logs show explicit `WATCH` versus `NO_TRADE` semantics.
- [ ] At least one replay/backtest evaluation confirms the new policy does not simply convert weak setups into trades.
