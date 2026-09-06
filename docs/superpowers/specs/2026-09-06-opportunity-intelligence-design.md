# Opportunity Intelligence Design

**Goal:** Make Production V2 explicitly discover, preserve, compare, and qualify profitable trading opportunities before asking the execution gates to authorize a trade.

## Problem

The current nine-engine pipeline is strong at rejecting unsafe or unproven trades, but the latest runtime example can let a recent counter-directional liquidity event dominate an earlier directional opportunity. In the 2026-09-06 BTC M5 example, E1/E2 described bullish/developing opportunity context while E4 reported a pending high-sweep rejection and E6 carried a SELL opportunity watch. The system correctly avoided a trade, but it did not preserve the competing BUY continuation idea as an explicit live opportunity.

## Design Principles

1. Opportunity quality and immediate trade economics are separate concepts.
2. A liquidity event is evidence for a thesis, not automatically the thesis itself.
3. BUY and SELL opportunities may coexist conditionally until evidence resolves the competition.
4. E6 remains the authoritative owner of a causal setup thesis; E7 cannot invent one.
5. E8 prices risk/reward only after a surviving E6 thesis exists.
6. E9 remains final governance and cannot manufacture an opportunity.
7. Closed M5 candles remain the only promotion/trigger clock.
8. Existing E4/E6 lifecycle surgery and re-entry semantics must remain intact.
9. No threshold is lowered merely to increase signal count.

## Opportunity Book

Introduce a central opportunity-book layer that stores independent directional candidates with stable identity and causal evidence. Each candidate carries direction, opportunity family, origin event/context, current lifecycle, quality/evidence fields, invalidation conditions, and conditional next evidence required.

The book supports multiple active candidates, normally one primary candidate and optional opposing candidate. It does not authorize execution. It provides a durable hypothesis surface to E6/E7 and the lifecycle system.

Canonical lifecycle:

`FORMING -> DEVELOPING -> THESIS_READY -> TRIGGER_PENDING -> EXECUTABLE`

Terminal states:

`INVALIDATED | EXPIRED | REPLACED | EXECUTED`

A candidate may remain `DEVELOPING` even when entry-now economics are poor. This is intentional: the system should be able to say “high-quality opportunity, wait for better location/confirmation.”

## Engine Responsibilities

### E1 — Context

Remain market-state/context owner. Add structured directional context/playbook preference only as evidence, never as a setup or trade recommendation.

### E2 — Opportunity Hunter

Transform E1 context and current market evidence into directional opportunity candidates. It should be able to emit conditional opportunities such as `BUY_IF_PULLBACK_AND_CONFIRMATION` or `SELL_IF_REJECTION_AND_FOLLOW_THROUGH` without claiming execution readiness.

### E3/E4/E5 — Evidence and Location

Continue to provide structure, liquidity/auction, and value/location evidence. Their outputs must enrich or weaken candidates without silently deleting an otherwise causal opportunity. Location quality and entry-now tradeability remain separate fields.

### E6 — Thesis Builder

Consume the Opportunity Book and upstream evidence to build/maintain the causal setup thesis. A new event may strengthen, weaken, or create a competing thesis, but event direction alone cannot replace the causal thesis.

### E7 — Trigger

Only confirm an existing E6 thesis. Conditional opportunities remain watch-only until setup-specific closed-candle confirmation exists.

### E8 — Economics

Evaluate stop, target, execution cost, RR, probability quality, and expected value only for a surviving E6 thesis. A weak entry location must not erase the underlying opportunity; it should produce a wait/poor-entry economic state.

### E9 — Governance

Resolve conflicts, apply final safety/risk gates, and authorize or reject execution. E9 must preserve visibility of competing opportunities and must not invent one.

## Opportunity Competition

For each candle, compare active BUY and SELL candidates using causal evidence, market-context alignment, structure, liquidity, location, confirmation state, and invalidation evidence. The result should identify the leading candidate, opposing candidate, unresolved competition, and the evidence that would promote or invalidate each. “Latest event wins” is explicitly prohibited.

## Opportunity Memory

Persist candidate identity and causal lineage across closed candles. A new candle should advance evidence rather than reset the candidate. A re-entry on the same causal setup is permitted after a prior execution when the existing project execution/re-entry rules allow it.

## Missed Opportunity Measurement

Record candidate outcomes independently from trade outcomes: confirmed winner, confirmed loser, invalidated, expired, or missed execution. This enables measurement of opportunity recall and false opportunity rate without changing live risk gates.

## Acceptance Criteria

- A bullish E1/E2 context and bearish pending E4 event can coexist as separate directional candidates.
- E6 does not automatically convert a latest liquidity event into the sole thesis.
- An opportunity with poor current entry economics can remain alive with explicit wait conditions.
- E7 never creates a thesis.
- E8 never creates an opportunity.
- E9 can block execution without deleting opportunity evidence.
- Existing lifecycle regression tests continue to pass.
- Same-candle processing remains idempotent.
- Closed-candle sequencing remains authoritative.
- No new implementation lowers existing risk thresholds or forces a trade.
