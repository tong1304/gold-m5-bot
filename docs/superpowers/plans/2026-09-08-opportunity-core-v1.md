# Opportunity Core V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish one canonical opportunity record and state vocabulary around the existing production-v2 lifecycle without changing E1-E9 authority or live execution behavior.

**Architecture:** Keep the current E1-E9 specialists and lifecycle adapter intact. Add `opportunity_core.py` as the canonical record/normalization boundary and `opportunity_state_machine.py` as the canonical stage vocabulary, then make `opportunity_lifecycle.py` emit those canonical fields while preserving all legacy fields consumed by the current pipeline, memory, alerts, and tests.

**Tech Stack:** Python 3, dataclasses, existing production_v2 lifecycle dictionaries, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-08-opportunity-core-v1.md`

## Global Constraints

- E9 remains the sole execution authority.
- E4 remains the causal-event timing anchor.
- No automatic order execution is introduced.
- Existing lifecycle keys remain backward-compatible.
- Do not delete surgery/legacy modules in this phase.
- Canonicalization must not rewrite upstream evidence.

---

### Task 1: Canonical Opportunity Record

**Files:**
- Create: `production_v2/opportunity_core.py`
- Test: `tests/test_opportunity_core_v1.py`

**Interfaces:**
- `OpportunityRecord.from_lifecycle(lifecycle, symbol, timeframe, *, edge_remaining=None) -> OpportunityRecord`
- `OpportunityRecord.as_dict() -> dict[str, Any]`
- `canonical_stage(lifecycle, *, e9_decision=None) -> str`

- [ ] Write failing tests for required fields, stable ID, event anchor, age, and stage mapping.
- [ ] Run the focused tests and verify they fail for the expected missing-module reason.
- [ ] Implement the minimal dataclass and canonical stage mapper.
- [ ] Run the focused tests until green.
- [ ] Refactor only for readability while keeping the interface stable.

### Task 2: Canonical State Machine

**Files:**
- Create: `production_v2/opportunity_state_machine.py`
- Test: `tests/test_opportunity_state_machine_v1.py`

**Interfaces:**
- `VALID_STAGES`
- `ALLOWED_TRANSITIONS`
- `can_transition(previous_stage, next_stage) -> bool`
- `transition(previous_stage, next_stage) -> str`

- [ ] Write failing tests for WATCH -> THESIS -> CONFIRMING -> ACTIONABLE -> TRADE and terminal invalidation/expiry/late paths.
- [ ] Run focused tests and verify red.
- [ ] Implement the minimal transition table and validation.
- [ ] Run focused tests and verify green.

### Task 3: Integrate Canonical Fields Into Existing Lifecycle

**Files:**
- Modify: `production_v2/opportunity_lifecycle.py`
- Test: `tests/test_opportunity_lifecycle.py` (extend existing lifecycle coverage if present)

**Interfaces:**
- Existing `advance_opportunity` and `advance_opportunity_directions` signatures remain compatible.
- Lifecycle output gains `canonical_stage` and `opportunity_record` without removing existing keys.

- [ ] Write failing regression tests showing the same Opportunity ID persists across candles and canonical stage remains WATCH/CONFIRMING rather than collapsing to NO_TRADE semantics.
- [ ] Run focused tests and verify red.
- [ ] Add canonicalization at lifecycle output boundaries.
- [ ] Run lifecycle and contract tests.
- [ ] Verify no upstream evidence fields are rewritten.

### Task 4: Pipeline Contract Regression

**Files:**
- Modify: `production_v2/contracts.py` only if required by failing tests.
- Test: `tests/test_pipeline_contract.py` and existing production-v2 contract tests.

- [ ] Add assertions that `DecisionResult` still exposes E9 as `decision_authority` and accepts the enriched lifecycle payload.
- [ ] Run focused contract tests.
- [ ] Run the production-v2 test suite available in CI.

### Task 5: Verification and Review

**Files:**
- No new production files unless a test exposes a defect.

- [ ] Run focused opportunity-core/state-machine/lifecycle tests.
- [ ] Run the complete available pytest suite.
- [ ] Inspect the resulting diff for accidental behavior changes.
- [ ] Verify branch contains no direct automatic order-execution changes.
- [ ] Create a pull request from `architecture/opportunity-core-v1` to `production-v2` for review before merging.
