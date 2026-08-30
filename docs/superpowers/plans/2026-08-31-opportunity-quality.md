# Opportunity Quality Without Signal Inflation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve trade-opportunity quality across E1-E9 without lowering hard risk gates or deliberately increasing trade frequency.

**Architecture:** Keep the existing sequential E1→E9 pipeline and E9 final authority. Improve evidence classification, counter-evidence weighting, setup staging, and economic geometry evaluation while preserving closed-candle/no-lookahead and hard risk vetoes.

**Tech Stack:** Python 3, pandas/numpy/scipy as already used by production-v2, pytest, existing EngineResult contracts.

**Spec:** `docs/superpowers/specs/2026-08-31-opportunity-quality-design.md`

## Global Constraints

- E9 remains the only execution authority.
- Do not lower MIN_RR, probability, stop-quality, target-realism, or execution-cost hard gates.
- Do not manufacture pending auction evidence as confirmed evidence.
- Do not introduce lookahead into pivot, auction, confirmation, or target calculations.
- Do not intentionally increase signal frequency; optimize quality of accepted trades and clarity of waiting states.
- Preserve duplicate-candle suppression and closed-candle-only evaluation.
- Keep pipeline order E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9.

---

### Task 1: E1 market-state evidence reconciliation

**Files:**
- Modify: `production_v2/e1_brain.py`
- Test: existing production-v2 test location if present; otherwise add `tests/test_e1_opportunity_quality.py`

**Interfaces:**
- Consumes: existing `analyze_e1(bars)` input.
- Produces: existing E1 output fields plus explicit directional evidence, counter-evidence severity, transition/range confidence, and next-event guidance without changing E1's authority boundary.

- [ ] **Step 1: Write the failing regression test** for a range/transition snapshot where EMA direction is down but structure is mixed. Assert E1 does not report a clean trend state merely because EMA20 is below EMA50.
- [ ] **Step 2: Run the focused test** with `pytest tests/test_e1_opportunity_quality.py -q` and verify failure against the current behavior.
- [ ] **Step 3: Implement minimal evidence reconciliation** so EMA, multi-horizon direction, persistence, volatility, and structure are separately represented and transition/range state wins when directional evidence lacks persistence.
- [ ] **Step 4: Add explicit counter-evidence weighting** so one weaker observation cannot masquerade as a hard invalidation.
- [ ] **Step 5: Run the focused E1 tests** and verify pass.
- [ ] **Step 6: Commit** with `git add production_v2/e1_brain.py tests/test_e1_opportunity_quality.py && git commit -m "refactor: reconcile E1 market state evidence"`.

### Task 2: E2 opportunity maturity and conditional paths

**Files:**
- Modify: `production_v2/e2_brain.py`
- Test: `tests/test_e2_opportunity_quality.py`

**Interfaces:**
- Consumes: closed-candle snapshot and E1 cross-check.
- Produces: existing opportunity candidate structure plus explicit `supporting_evidence`, `counter_evidence`, `missing_evidence`, `opportunity_maturity`, and conditional next-event states.

- [ ] **Step 1: Write failing tests** for `SELL_SIDE_ACCEPTANCE` pending follow-through and for a directional candidate with sufficient evidence but no terminal auction confirmation.
- [ ] **Step 2: Run focused tests** and verify failure.
- [ ] **Step 3: Refine candidate veto semantics** so descriptive evidence scores never authorize a trade and pending acceptance is represented as a maturity state rather than an opaque unresolved condition.
- [ ] **Step 4: Ensure the exact next closed-candle event is emitted** for each immature candidate.
- [ ] **Step 5: Run focused E2 tests** and verify pass.
- [ ] **Step 6: Commit** with `git add production_v2/e2_brain.py tests/test_e2_opportunity_quality.py && git commit -m "refactor: improve E2 opportunity maturity"`.

### Task 3: E3 external-versus-internal structure reconciliation

**Files:**
- Modify: `production_v2/e3_brain.py`
- Test: `tests/test_e3_structure_reconciliation.py`

**Interfaces:**
- Consumes: closed-candle OHLC.
- Produces: existing causal structure output with explicit external/internal relationship and counter-evidence classification.

- [ ] **Step 1: Write a failing test** using the supplied pattern: external DOWN, internal UP, no BOS/CHOCH. Assert the internal UP state is not automatically a hard thesis conflict when it is a plausible retracement.
- [ ] **Step 2: Run the focused test** and verify failure.
- [ ] **Step 3: Implement a bounded retracement classifier** using confirmed pivots, protected levels, and no-lookahead event timing.
- [ ] **Step 4: Mark true structural invalidation only when protected structure is causally broken**, not when an internal counter-swing exists.
- [ ] **Step 5: Run focused E3 tests** and verify pass.
- [ ] **Step 6: Commit** with `git add production_v2/e3_brain.py tests/test_e3_structure_reconciliation.py && git commit -m "refactor: distinguish E3 retracement from invalidation"`.

### Task 4: E4 auction lifecycle quality

**Files:**
- Modify: `production_v2/e4_brain.py`
- Test: `tests/test_e4_auction_quality.py`

**Interfaces:**
- Consumes: snapshot plus E1/E3 evidence.
- Produces: existing stateful auction lifecycle with event identity, liquidity quality, acceptance/rejection, and follow-through evidence.

- [ ] **Step 1: Write failing tests** for internal equal-liquidity low acceptance and external low sweep rejection. Assert both remain pending until causal follow-through requirements are met.
- [ ] **Step 2: Run focused tests** and verify failure.
- [ ] **Step 3: Preserve event identity and frozen ATR** while separating internal versus external liquidity information weight.
- [ ] **Step 4: Require causal follow-through on the event's subsequent closed candle(s)** before terminal acceptance.
- [ ] **Step 5: Emit `next_required_event` and `counter_evidence` consistently for pending auctions.
- [ ] **Step 6: Run focused E4 tests** and verify pass.
- [ ] **Step 7: Commit** with `git add production_v2/e4_brain.py tests/test_e4_auction_quality.py && git commit -m "refactor: strengthen E4 auction lifecycle"`.

### Task 5: E5 location and direction-specific space

**Files:**
- Modify: `production_v2/e5_brain.py`
- Test: `tests/test_e5_tradeable_space.py`

**Interfaces:**
- Consumes: snapshot plus E1/E3/E4 evidence.
- Produces: existing location/value output with direction-specific structural space, target candidates, extension, and counter-evidence.

- [ ] **Step 1: Write failing tests** for the logged case where short space is about 0.34 ATR and long space is materially larger. Assert E5 does not label the short side executable merely because location is favorable.
- [ ] **Step 2: Run focused tests** and verify failure.
- [ ] **Step 3: Separate `location_state` from `execution_space_state`** and preserve value response as contextual evidence only.
- [ ] **Step 4: Expose nearest usable structural target and target clearance in ATR units** without fabricating levels.
- [ ] **Step 5: Run focused E5 tests** and verify pass.
- [ ] **Step 6: Commit** with `git add production_v2/e5_brain.py tests/test_e5_tradeable_space.py && git commit -m "refactor: improve E5 tradeable space analysis"`.

### Task 6: E6 setup staging and counter-evidence weighting

**Files:**
- Modify: `production_v2/e6_brain.py`
- Test: `tests/test_e6_setup_staging.py`

**Interfaces:**
- Consumes: E1-E5 `EngineResult` evidence.
- Produces: existing setup lifecycle with `FORMING`, `VALIDATING`, `MATURE`, explicit thesis/support/counter/missing evidence, and no execution authority.

- [ ] **Step 1: Write failing tests** for a bearish external structure with bullish internal retracement and for a pending auction with insufficient opposing space.
- [ ] **Step 2: Run focused tests** and verify failure.
- [ ] **Step 3: Treat normal internal retracement as supporting context when it does not break protected structure.
- [ ] **Step 4: Make setup maturity depend on independent evidence classes rather than raw count of upstream reasons.
- [ ] **Step 5: Emit the precise gate that would move the setup from VALIDATING to MATURE.
- [ ] **Step 6: Run focused E6 tests** and verify pass.
- [ ] **Step 7: Commit** with `git add production_v2/e6_brain.py tests/test_e6_setup_staging.py && git commit -m "refactor: improve E6 setup staging"`.

### Task 7: E7 confirmation versus entry trigger

**Files:**
- Modify: `production_v2/e7_brain.py`
- Test: `tests/test_e7_confirmation.py`

**Interfaces:**
- Consumes: E4/E6 evidence and closed candles.
- Produces: setup confirmation state and current-candle trigger state independently.

- [ ] **Step 1: Write failing regression tests** for a confirmed causal setup without a valid current entry trigger and for a valid trigger without setup confirmation.
- [ ] **Step 2: Run focused tests** and verify failure.
- [ ] **Step 3: Keep `confirmation_state` and `trigger_state` independent.
- [ ] **Step 4: Ensure `CONFIRMATION_PROVEN` cannot by itself produce a trade-ready result.
- [ ] **Step 5: Emit missing proof and next required event without inventing trigger evidence.
- [ ] **Step 6: Run focused E7 tests** and verify pass.
- [ ] **Step 7: Commit** with `git add production_v2/e7_brain.py tests/test_e7_confirmation.py && git commit -m "refactor: separate E7 confirmation from trigger"`.

### Task 8: E8 geometry optimization without gate relaxation

**Files:**
- Modify: `production_v2/e8_brain.py`
- Test: `tests/test_e8_geometry.py`

**Interfaces:**
- Consumes: E5/E6/E7 evidence and snapshot.
- Produces: existing economic/risk decision plus evaluated defensible entry/stop/target geometry and explicit rejection reasons.

- [ ] **Step 1: Write failing tests** for the logged `short_space < 0.75 ATR` case and for a case where an alternative structurally valid entry improves real RR without violating stop/target gates.
- [ ] **Step 2: Run focused tests** and verify failure.
- [ ] **Step 3: Generate only structurally defensible geometry candidates** from existing entry context, protected levels, liquidity levels, and value levels; never invent arbitrary target prices.
- [ ] **Step 4: Evaluate each candidate against unchanged MIN_RR, target realism, stop quality, survival, execution-cost, and probability gates.
- [ ] **Step 5: Select the highest-quality valid geometry if one exists; otherwise retain the hard rejection.
- [ ] **Step 6: Emit `geometry_candidates_evaluated`, `selected_geometry`, and `geometry_rejection_reasons` for auditability.
- [ ] **Step 7: Run focused E8 tests** and verify pass.
- [ ] **Step 8: Commit** with `git add production_v2/e8_brain.py tests/test_e8_geometry.py && git commit -m "refactor: optimize E8 trade geometry without relaxing risk"`.

### Task 9: E9 evidence reconciliation and governance

**Files:**
- Modify: `production_v2/e9_brain.py`
- Test: `tests/test_e9_governance.py`

**Interfaces:**
- Consumes: E1-E8 evidence through the existing boundary.
- Produces: final BUY/SELL/NO_TRADE decision with reproducible governance trace and deduplicated conflict classes.

- [ ] **Step 1: Write failing tests** showing duplicated upstream blockers should not be counted as independent conflicts, while a true protected-structure invalidation remains hard.
- [ ] **Step 2: Run focused tests** and verify failure.
- [ ] **Step 3: Group repeated evidence by causal source and retain only the strongest representative blocker for governance scoring.
- [ ] **Step 4: Preserve every hard conflict and economic blocker in the final audit trail.
- [ ] **Step 5: Prevent E9 from treating pending auction states or descriptive opportunity scores as confirmation.
- [ ] **Step 6: Run focused E9 tests** and verify pass.
- [ ] **Step 7: Commit** with `git add production_v2/e9_brain.py tests/test_e9_governance.py && git commit -m "refactor: reconcile E9 governance evidence"`.

### Task 10: Opportunity audit metrics and pipeline regression

**Files:**
- Modify: `production_v2/professional_brain_audit.py`
- Modify: `production_v2/pipeline.py` only if required by the contract changes
- Test: `tests/test_professional_audit.py` and `tests/test_pipeline_regression.py`

**Interfaces:**
- Consumes: all nine engine outputs.
- Produces: non-authoritative professional quality scores and latent opportunity metrics; pipeline still returns only E9-authorized execution decisions.

- [ ] **Step 1: Write failing tests** for opportunity potential: a high-quality waiting setup should score as WATCH rather than executable, and a hard economic veto must remain non-executable.
- [ ] **Step 2: Run focused tests** and verify failure.
- [ ] **Step 3: Improve the audit metric to distinguish evidence quality, trade geometry quality, and readiness; do not interpret latent score as expected profit.
- [ ] **Step 4: Update pipeline only where required to pass the new explicit fields; preserve sequential architecture and E9 authority.
- [ ] **Step 5: Run focused audit/pipeline tests** and verify pass.
- [ ] **Step 6: Run the complete pytest suite.
- [ ] **Step 7: Commit** with `git add production_v2/professional_brain_audit.py production_v2/pipeline.py tests && git commit -m "test: validate opportunity quality governance"`.

### Task 11: Production regression verification

**Files:**
- Modify: only files required by failing tests; no unrelated refactors.
- Test: full existing suite plus targeted regression fixtures.

**Interfaces:**
- Consumes: complete production-v2 pipeline.
- Produces: verified NO_TRADE behavior for invalid setups and verified trade approval only when all hard gates pass.

- [ ] **Step 1: Run `pytest -q` from the repository root.
- [ ] **Step 2: Run the pipeline against the supplied BTC scenarios: transition/range, E3 external DOWN/internal UP, E4 pending low acceptance, E5 short-space constrained, E7 confirmation proven, E8 invalid geometry.
- [ ] **Step 3: Assert the system remains `NO_TRADE` for the supplied invalid geometry case and that the reason trail identifies the decisive gate rather than a duplicated list.
- [ ] **Step 4: Assert duplicate candle input is skipped and does not cause a second evaluation.
- [ ] **Step 5: Inspect the final nine-brain audit to confirm no engine has gained execution authority.
- [ ] **Step 6: Commit any regression-only fixes separately with `git commit -m "fix: preserve production-v2 regression behavior"`.
