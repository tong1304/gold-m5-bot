# Production V2 Major Repair Specification

**Date:** 2026-09-05  
**Scope:** Production V2 lifecycle, persistence, decision/execution boundary, E2/E5/E6-E9 semantics, observability, and end-to-end verification.

## Goal

Make Production V2 behave as a deterministic professional-trader pipeline: identify causal opportunity, wait for closed-candle confirmation, validate trade economics, issue an E9 decision, and only then hand off to an explicit execution state machine. A decision must never be represented as an executed order.

## Non-negotiable constraints

- M5 closed-candle-only remains mandatory.
- No lookahead remains forbidden.
- E9 remains final decision authority.
- Do not lower signal thresholds to increase trade count.
- E7 cannot manufacture a thesis that E6 did not establish.
- E8 cannot make an inapplicable setup tradeable.
- Lifecycle persistence must survive process restart when persistent storage is configured.
- Decision state and broker/execution state must be separate.

## Target architecture

```text
Market Data
  -> E1 -> E2 -> E3 -> E4 -> E5 -> E6
  -> E7 Confirmation
  -> E8 Economics/Risk
  -> E9 Final Governance
  -> Opportunity Lifecycle
  -> Execution State Machine
```

E1-E9 remain sequential. Lifecycle records opportunity continuity but grants no execution authority. E9 produces an authorization/decision; an execution adapter records what actually happened.

## 1. Canonical lifecycle

`production_v2/opportunity_lifecycle.py` becomes the sole lifecycle transition authority. Remove semantic duplication between `advance_opportunity()` and `advance_lifecycle()` by defining one canonical transition API and a stable state vocabulary.

Canonical opportunity states:

- `IDLE`
- `WATCHING`
- `WAITING`
- `READY`
- `INVALIDATED`
- `EXPIRED`
- `REPLACED`
- `EXECUTED`

`EXECUTED` means an execution event has actually been accepted/opened by the execution layer, not merely that E9 approved a trade.

The lifecycle record must contain at minimum: `opportunity_id`, direction, setup, state, origin candle, last evaluated candle, bars waited, wait-for reason(s), invalidation reason, and execution reference/state when present.

## 2. Persistent memory

`production_v2/opportunity_memory.py` must prefer a configured persistent database in production. A transient `/tmp` file must not silently become the production source of truth. If PostgreSQL is configured and unavailable, the application must report degraded/unhealthy state rather than silently falling back to transient memory.

File persistence may remain as an explicit development/test backend only.

## 3. Single lifecycle owner

`production_v2/app.py` and `production_v2/pipeline.py` must not independently advance the same opportunity. There must be one lifecycle transition call and one persisted state write per evaluation. Runtime wrappers must enrich the result, not create a second state machine.

## 4. E2 semantics

E2 remains an opportunity/regime evidence source. `UNRESOLVED` or `DEVELOPING` must not be treated as positive confirmation, but it must not be conflated with a fatal veto when downstream causal evidence can legitimately remain in watch mode. Hard contradictions still block the setup.

## 5. E5 semantics

Separate:

- location is favorable;
- setup has enough structural space;
- trade is economically viable.

`FAVORABLE_LOCATION` must never imply `TRADEABLE`. E5 should expose explicit space/structural constraints for downstream E6/E8.

## 6. E6 -> E7 -> E8 -> E9 boundary

- E6 establishes or watches a causal setup from E1-E5.
- E7 validates a setup-specific closed-candle trigger; it cannot create the setup thesis.
- E8 validates risk, available space, costs, RR and profit-edge trustworthiness.
- E9 makes the final governance decision.

A watch state must remain a watch state until the required causal/confirmation evidence exists.

## 7. Execution boundary

Introduce explicit execution states:

`NONE -> ORDER_INTENT -> ORDER_SUBMITTED -> ACCEPTED/REJECTED -> POSITION_OPEN -> POSITION_CLOSED`

An E9 `BUY`/`SELL` decision is an authorization event, not proof of broker execution. The execution layer must expose an event/state interface that statistics and lifecycle can consume.

## 8. Statistics

`production_v2/statistics.py` must stop counting `result.decision in {BUY, SELL} and gate_passed` as a trade. It may count decisions separately, while actual trades/open positions are counted from explicit execution events.

## 9. Observability

Every lifecycle/execution transition must be attributable to symbol, opportunity ID, candle, previous state, next state, E9 decision, execution state, and reason. Duplicate candles remain idempotent and must not advance lifecycle or execution state twice.

## 10. Verification requirements

Tests must prove:

1. watch opportunity persists across a new closed candle;
2. watch can promote to setup only with causal evidence;
3. E7 cannot create a thesis;
4. E8 is not applicable without a surviving setup;
5. E9 cannot report execution merely because it approves;
6. execution state transitions are explicit;
7. rejected execution does not become `EXECUTED`;
8. restart reloads persistent lifecycle state;
9. duplicate candles are idempotent;
10. invalidation/expiry/replacement work deterministically;
11. closed-candle-only/no-lookahead behavior remains intact;
12. the full happy path reaches `E9 TRADE -> ORDER_INTENT` and only an execution acceptance/open event reaches `EXECUTED`.

## Success criterion

The system must be able to explain, for every candidate, exactly why it is watching, waiting, ready, blocked, invalidated, expired, replaced, authorized, or actually executed. No layer may infer execution from a decision alone.
