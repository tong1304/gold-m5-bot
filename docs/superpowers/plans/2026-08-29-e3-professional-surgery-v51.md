# E3 Professional Structure Surgery v51 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `production_v2/e3_brain.py` so E3 explicitly reasons in professional market-structure semantics: HH/HL/LH/LL, BOS, CHOCH, protected structure, authority, invalidation, current-vs-historical lifecycle, and a locked E3/E4 contract.

**Architecture:** Keep E3 autonomous and independent of upstream trade decisions. E3 remains a descriptive market-structure brain; E4 remains the specialist responsible for independent liquidity/event evidence. E3 may report structural liquidity observations but must not convert them into E4 confirmation or trade authority.

**Tech Stack:** Python 3, pytest, existing Production V2 pipeline.

**Spec:** User-approved E3 MARKET STRUCTURE contract supplied in conversation on 2026-08-29.

## Global Constraints

- E3 consumes only its candle input and does not use E1/E2 direction, gates, scores, or decisions.
- Only closed candles may confirm structure, BOS, CHOCH, liquidity, and invalidation.
- Counts are descriptive only; ordered swing semantics are authoritative.
- External structure has directional authority over internal structure.
- Historical events never override the current structural state.
- E3 never makes a trade decision; E9 remains the only decision authority.
- E4 remains responsible for independent liquidity/event confirmation.

---

### Task 1: Add failing E3 contract tests

**Files:**
- Create: `tests/test_e3_professional_structure.py`

**Interfaces:**
- Consumes: `production_v2.e3_brain.analyze_e3()` and exported E3 helpers.
- Produces: executable regression coverage for semantic labels, CHOCH, protected structure, explicit authority, invalidation semantics, and E3/E4 separation.

- [ ] **Step 1: Write failing tests**
  - Assert output exposes explicit semantic swing sequences containing HH/HL/LH/LL where the input creates them.
  - Assert a closed-candle break against a directional protected level reports `CONFIRMED_CHOCH`, not only a generic mixed state.
  - Assert protected structure contains active anchor metadata and a concrete invalidation level whenever a valid directional sequence exists.
  - Assert authority is an explicit object with `authority`, `direction`, `source`, and `actionable` fields, and internal structure cannot become authority by count disagreement.
  - Assert invalidation exposes `VALID`/`INVALIDATED` semantic status and explains whether the protected thesis is invalidated without declaring a reversal.
  - Assert E3 liquidity output is structural observation only and explicitly marks E4 confirmation as required; E3 cannot claim E4 specialist confirmation.

- [ ] **Step 2: Run tests and verify they fail**
  - Run: `pytest tests/test_e3_professional_structure.py -q`
  - Expected: FAIL on the new contract fields/CHOCH semantics.

### Task 2: Implement E3 semantic/protected-structure upgrade

**Files:**
- Modify: `production_v2/e3_brain.py`

**Interfaces:**
- Consumes: existing candle-only E3 input.
- Produces: stable E3 output preserving existing fields while adding explicit professional semantics.

- [ ] **Step 1: Implement ordered HH/HL/LH/LL semantic sequence metadata**
  - Preserve current descriptive counts.
  - Add explicit swing-role records and directional sequence metadata.
  - Make semantic state depend on ordered structural relationships, not counts.

- [ ] **Step 2: Implement protected structure from the latest valid directional leg**
  - For UP, protect the latest valid HL supporting the latest HH.
  - For DOWN, protect the latest valid LH supporting the latest LL.
  - Mark anchor status/quality explicitly and expose the invalidation condition.

- [ ] **Step 3: Implement explicit CHOCH detection**
  - Detect a closed-candle break through the currently protected counter-structure level against the prior directional thesis.
  - Require the same close-quality/displacement rules used for structural breaks.
  - Emit `CONFIRMED_CHOCH` with source scope and level rather than hiding the event behind `MIXED_STRUCTURE`.

- [ ] **Step 4: Harden invalidation semantics**
  - Emit `status=VALID` or `status=INVALIDATED`.
  - Tie invalidation directly to the active protected level and closed-candle acceptance.
  - Keep `does_not_confirm_reversal=true`.

- [ ] **Step 5: Lock authority semantics**
  - Return an explicit authority object.
  - External structure is authoritative only when directional and not invalidated.
  - Internal structure remains context-only.
  - Counts never grant authority.

- [ ] **Step 6: Lock E3/E4 contract**
  - E3 reports structural liquidity facts only.
  - Add explicit `e4_confirmation_required=true` and `specialist_confirmation=false` semantics to E3 liquidity output.
  - Preserve E4 as the independent specialist confirmation layer.

- [ ] **Step 7: Run targeted tests**
  - Run: `pytest tests/test_e3_professional_structure.py -q`
  - Expected: PASS.

### Task 3: Regression verification

**Files:**
- No additional production files unless tests expose a required compatibility fix.

- [ ] **Step 1: Run all tests**
  - Run: `pytest -q`
  - Expected: PASS.

- [ ] **Step 2: Verify pipeline compatibility**
  - Confirm `analyze_e3()` remains importable and returns the existing top-level keys consumed by E4/E9.
  - Confirm E3 remains `decision_authority=E9_ONLY` and does not activate trade gates.

- [ ] **Step 3: Inspect final diff**
  - Confirm only E3 and its focused regression tests/docs changed.
  - Confirm no E1/E2/E4/E5/E6/E7/E8/E9 behavior was intentionally modified.
