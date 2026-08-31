# Opportunity Discovery & Professional Trade Economics Surgery

## Scope

Strengthen the existing Production V2 E6-E9 decision chain so the system can explicitly detect, preserve, test, and economically validate profitable opportunities without manufacturing trades. E1-E5 remain the market-evidence foundation and are not behaviorally rewritten in this surgery.

## Current evidence

Recent production logs show strong closed-candle discipline, causal structure/liquidity analysis, location/value analysis, and conservative governance. The main weakness is that a valid E6 thesis can be lost at E9 (`thesis=UNRESOLVED`, `setup=UNKNOWN`) and E8 is primarily a rejection gate rather than a complete economic opportunity evaluator.

Existing E6 already supports event-backed candidate formation and has a minimum-space diagnostic; existing E8 already has structural target/stop, MAE, RR, probability, sensitivity and execution-cost concepts; existing E9 already separates market control, E6 thesis ownership, E7 proof, and E8 economics. The surgery should strengthen these contracts rather than replace the architecture.

## Design

### E6 — Opportunity Thesis Engine

E6 remains the owner of the trade thesis. A thesis is a hypothesis, not a signal.

Every surviving candidate must preserve:
- direction
- setup family
- causal catalyst/event
- thesis lifecycle
- supporting evidence
- counter-evidence
- invalidation condition
- next required evidence
- entry concept
- structural invalidation concept
- space diagnostic
- competing thesis when present

Lifecycle: `ABSENT -> FORMING -> VALIDATING -> MATURE`, with explicit `FAILED`, `INVALIDATED`, and `EXPIRED` exits.

E6 may FORM a setup before E2 is fully confirmed only when there is a concrete E3/E4 causal event. It may never promote that hypothesis to trade-ready without E7 and E8.

### E7 — Setup-Specific Proof Engine

E7 evaluates only the E6 thesis and never creates a new thesis.

The output must distinguish:
- observed evidence
- required evidence
- missing evidence
- confirmation state
- closed-candle trigger state
- follow-through state
- invalidation state
- next required event

A trigger is not confirmation. Confirmation is not economic approval.

### E8 — Professional Trade Economics

E8 remains direction-neutral and setup-neutral. It evaluates whether the E6/E7 trade idea has positive and robust geometry.

For a proposed direction it should preserve an auditable chain:
`entry -> structural stop -> opposing structural target -> gross RR -> execution-adjusted RR -> effective space -> survival -> probability -> expectancy -> robustness`.

Hard gates include:
- structurally invalid or missing stop
- no credible opposing structural target
- insufficient effective space
- RR below configured minimum after realistic costs
- target realism below threshold
- stop quality below threshold
- insufficient historical sample for probability claims
- probability edge not trustworthy
- profit edge not proven
- expectancy unquantified
- sensitivity/robustness failure

E8 must not invent probability when sample quality is insufficient. It should expose `UNRESOLVED` economics rather than fabricate confidence.

### E9 — Opportunity Governor

E9 is the final governance layer and must preserve E6 identity even when E7/E8 reject it.

The final state should be able to distinguish:
- `NO_TRADE`
- `WATCH`
- `SETUP_READY`
- `TRADE_READY`

A rejected thesis must remain auditable, e.g.:
`thesis=BUY BREAKOUT_RETEST`, `thesis_state=VALIDATING`, `E7=PENDING`, `E8=BLOCKED`, `decision=NO_TRADE`.

`UNKNOWN` is reserved for genuinely absent/undetectable thesis identity, not for a known thesis that failed a downstream gate.

## Invariants

1. Closed-candle-only evidence remains mandatory.
2. No lookahead remains mandatory.
3. E1-E5 remain evidence providers, not signal generators.
4. E6 owns setup identity.
5. E7 cannot invent a setup.
6. E8 cannot change direction or create a setup.
7. E9 cannot manufacture a trade.
8. NO_TRADE remains valid and preferred whenever proof/economics fail.
9. A stronger opportunity detector must not lower risk gates just to increase signal count.
10. Re-entry of the same setup remains possible only when the setup-specific proof and economic gates are independently valid.

## Validation plan

Test fixtures should cover:
1. No opportunity: all downstream states remain no-trade.
2. Causal setup hypothesis with incomplete E7 proof: E6 identity survives E9, decision remains no-trade.
3. Confirmed setup with invalid economics: E6/E7 identity survives E9, E8 blocks trade.
4. Fully proven setup with valid geometry/economics: E9 can reach `TRADE_READY`.
5. Thesis invalidation: E9 reports invalidated rather than unknown.
6. Insufficient historical sample: probability remains untrusted and cannot pass economics.
7. Conflicting structure/space: opportunity remains visible as a hypothesis but cannot become trade-ready.

## Success criteria

The surgery is successful when the system can simultaneously do two things:

- **See and preserve a real opportunity hypothesis early enough to evaluate it.**
- **Refuse to trade that opportunity until setup proof and economic edge are actually demonstrated.**

This targets professional decision architecture, not a guaranteed win rate or guaranteed profitability.
