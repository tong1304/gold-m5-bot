# Nine-Brain Opportunity Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make E1→E9 operate as one professional opportunity lifecycle, preserving evidence and the current wait state across closed candles without forcing trades.

**Architecture:** Add a small handoff layer that creates compact, typed context packets from each brain and a lifecycle state object for the current symbol/setup. Each downstream brain receives the prior handoff plus its declared upstream evidence; unresolved opportunities remain WATCH/WAIT instead of being discarded. E9 remains the only execution authority.

**Tech Stack:** Python 3.11+, existing production_v2 pipeline, pytest, dataclasses/standard library only.

**Spec:** Existing approved design in conversation: E1 State → E2 Opportunity → E3 Structure → E4 Auction/Liquidity → E5 Location/Space → E6 Thesis → E7 Confirmation → E8 Economics → E9 Governance.

## Global Constraints

- Closed-candle data only.
- No lookahead.
- No threshold loosening solely to increase signal count.
- E9 remains the only BUY/SELL authority.
- Preserve specialist evidence; downstream brains may not rewrite upstream facts.
- Historical probability remains distinct from uncalibrated bootstrap assumptions.
- A pending opportunity must expose what event it is waiting for.

---

### Task 1: Handoff contract

**Files:**
- Create: `production_v2/brain_handoff.py`
- Test: `production_v2/test_brain_handoff.py`

**Interfaces:**
- `build_handoff(engine_id, output, upstream_outputs) -> dict[str, Any]`
- `build_lifecycle(results) -> dict[str, Any]`

- [ ] Write failing tests for evidence preservation, direction, stage, next-required-event, and non-authority.
- [ ] Run tests and verify the expected failures.
- [ ] Implement compact handoff/lifecycle helpers.
- [ ] Run tests and verify green.

### Task 2: Sequential pipeline integration

**Files:**
- Modify: `production_v2/pipeline.py`
- Test: `production_v2/test_brain_handoff.py`

- [ ] Write failing integration assertions that E2 receives E1 handoff, E6 receives E1–E5 handoffs, and E9 receives the complete chain.
- [ ] Run tests and verify failure.
- [ ] Integrate handoff packets after every brain and expose `brain_handoffs`, `opportunity_lifecycle`, and `next_required_event` in the final risk payload.
- [ ] Preserve the existing specialist calls and E9 authority.
- [ ] Run focused tests.

### Task 3: Closed-candle lifecycle continuity

**Files:**
- Modify: `production_v2/pipeline.py`
- Test: `production_v2/test_brain_handoff.py`

- [ ] Add a test proving a pending opportunity is retained as WAITING rather than converted to a fresh unrelated opportunity within the pipeline instance.
- [ ] Implement per-pipeline in-memory lifecycle continuity keyed by symbol/setup direction, with invalidation/expiry clearing.
- [ ] Keep `resume_state` backward-compatible and do not persist fabricated state.
- [ ] Run focused tests.

### Task 4: Verification

**Files:**
- No production changes unless tests expose an issue.

- [ ] Run the handoff tests.
- [ ] Run existing production_v2 tests that are available.
- [ ] Compile changed modules.
- [ ] Confirm E9 still fails closed on governance/contract violations.
