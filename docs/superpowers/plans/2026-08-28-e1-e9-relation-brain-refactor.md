# E1-E9 Relation Brain Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (recommended) to implement this plan task-by-task.

**Goal:** Make E1-E9 nine independent professional reasoning brains on one cognitive axis, with relation-based evidence flow and E9 as the sole final decision authority.

**Architecture:** Each `eX_brain.py` owns one professional question and reasons independently within that scope. Engines receive only declared related upstream evidence; no sub-engines, peer-analysis waves, or parallel brain implementations. E9 receives the completed evidence set and alone decides BUY/SELL/NO_TRADE.

**Tech Stack:** Python, existing `EngineResult`/`DecisionResult` contracts, pytest, GitHub Actions/Render runtime.

**Spec:** `docs/superpowers/plans/2026-08-28-e1-e9-relation-brain-refactor.md`

## Global Constraints

- Exactly one active brain file per engine: `e1_brain.py` through `e9_brain.py`.
- No Sub-Engine architecture.
- No parallel peer-analysis architecture.
- No `professional_brain` as a second decision axis.
- Each engine may disagree with upstream evidence.
- Each engine must answer only its own professional question.
- E9 is the sole final trade-decision authority.
- Preserve infrastructure/data/notification responsibilities outside the brain files.

---

### Task 1: Establish relation-based evidence routing

**Files:**
- Modify: `production_v2/pipeline.py`
- Modify: `production_v2/engines.py`
- Test: existing pipeline/engine tests

- [ ] Define the explicit relation map E1→E2/E3, E1+E3→E4, E1+E3+E4→E5, E1-E5→E6, E4+E6→E7, E5+E6+E7→E8, E1-E8→E9.
- [ ] Pass only declared upstream results into each engine.
- [ ] Verify no parallel peer-analysis path remains active.
- [ ] Verify pipeline metadata reports relation-based evidence flow.

### Task 2: Remove competing brain paths

**Files:**
- Modify/delete obsolete production_v2 brain patches and duplicate brain implementations.
- Modify: any runtime imports that reference obsolete brain paths.

- [ ] Search for `professional_brain`, `*_brain_v*`, `sub_engine`, `peer_analysis`, and specialist-engine imports.
- [ ] Remove runtime dependencies on those paths.
- [ ] Keep non-brain infrastructure only where required.

### Task 3: Operate on E1 only

**Files:**
- Modify: `production_v2/e1_brain.py`
- Test: E1 tests

- [ ] Define E1's single professional question: What is the current market state/regime?
- [ ] Analyze closed-candle market state independently.
- [ ] Produce state, evidence, counter-evidence, confidence, invalidation and handoff evidence.
- [ ] Do not authorize a trade.

### Task 4: Operate on E2 only

**Files:**
- Modify: `production_v2/e2_brain.py`
- Test: E2 tests

- [ ] Define E2's question: What opportunity is the market offering now?
- [ ] Use E1 only as related evidence/cross-check.
- [ ] Form an independent opportunity thesis and counter-thesis.
- [ ] Never produce execution authority.

### Task 5: Operate on E3 only

**Files:**
- Modify: `production_v2/e3_brain.py`
- Test: E3 tests

- [ ] Define E3's question around market structure.
- [ ] Evaluate swing structure, breaks, continuation/invalidation independently.
- [ ] Report structural evidence, not trade decisions.

### Task 6: Operate on E4 only

**Files:**
- Modify: `production_v2/e4_brain.py`
- Test: E4 tests

- [ ] Define E4's liquidity question.
- [ ] Use only E1/E3 evidence plus raw market data.
- [ ] Detect liquidity events, sweeps, acceptance/rejection and invalidation.

### Task 7: Operate on E5 only

**Files:**
- Modify: `production_v2/e5_brain.py`
- Test: E5 tests

- [ ] Define E5's location/value question.
- [ ] Judge whether price is at a professional location with sufficient space.
- [ ] Challenge upstream assumptions where location contradicts the thesis.

### Task 8: Operate on E6 only

**Files:**
- Modify: `production_v2/e6_brain.py`
- Test: E6 tests

- [ ] Define E6's setup question.
- [ ] Synthesize E1-E5 evidence without blindly voting.
- [ ] Require a mature, coherent setup and explicit invalidation.

### Task 9: Operate on E7 only

**Files:**
- Modify: `production_v2/e7_brain.py`
- Test: E7 tests

- [ ] Define E7's confirmation/trigger question.
- [ ] Require observable confirmation rather than prediction.
- [ ] Reject setup when trigger evidence is absent or contradictory.

### Task 10: Operate on E8 only

**Files:**
- Modify: `production_v2/e8_brain.py`
- Test: E8 tests

- [ ] Define E8's trade-economics/risk question.
- [ ] Evaluate entry, invalidation, stop, targets, RR, available space and risk geometry.
- [ ] Never decide BUY/SELL itself.

### Task 11: Make E9 the sole final judge

**Files:**
- Modify: `production_v2/e9_brain.py`
- Test: E9 tests

- [ ] Consume E1-E8 evidence.
- [ ] Reconcile agreement, disagreement and counter-evidence.
- [ ] Decide BUY, SELL or NO_TRADE.
- [ ] Never delegate final authority to another brain.

### Task 12: Full verification

**Files:**
- Test: full test suite and runtime smoke tests

- [ ] Run syntax/import checks.
- [ ] Run unit tests for E1-E9.
- [ ] Run pipeline tests proving relation routing.
- [ ] Verify no forbidden duplicate/sub-engine imports remain.
- [ ] Verify E9 is the only final decision authority.
- [ ] Verify deployment/runtime health before claiming completion.
