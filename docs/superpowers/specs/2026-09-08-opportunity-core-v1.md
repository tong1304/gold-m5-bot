# Opportunity Core V1 Design Spec

## Goal
Make `production_v2` track a live trading opportunity as a durable stateful object instead of treating every M5 candle as an independent signal decision.

## Design
The existing E1-E9 specialists remain intact. `opportunity_lifecycle.py` remains the compatibility/runtime adapter, while two new canonical modules define the shared vocabulary: `opportunity_core.py` owns the opportunity record shape and `opportunity_state_machine.py` owns canonical stage semantics. This first migration is additive and backward-compatible; existing lifecycle keys and E9 authority remain unchanged.

## Canonical stages
- `IDLE`
- `WATCH`
- `THESIS`
- `CONFIRMING`
- `ACTIONABLE`
- `TRADE`
- `INVALIDATED`
- `EXPIRED`
- `TOO_LATE`

`WATCH` is not `NO_TRADE`; `CONFIRMING` is not `INVALIDATED`.

## Required record fields
`opportunity_id`, `symbol`, `timeframe`, `direction`, `setup`, `event_anchor`, `origin_candle`, `last_evaluated_candle`, `age_bars`, `stage`, `thesis_state`, `confirmation_state`, `invalidation_reason`, `execution_zone`, `edge_remaining`, `decision_authority`.

## Invariants
1. The causal E4 event remains the timing anchor.
2. An active opportunity keeps the same ID across candles unless a new causal event replaces it or the direction changes.
3. E9 remains the only execution authority.
4. Canonicalization must never rewrite upstream evidence.
5. Existing production lifecycle fields remain available for compatibility.
6. No automatic order execution is introduced.

## Migration strategy
Introduce canonicalization around the existing lifecycle instead of deleting surgery/legacy modules. Future phases can move ownership into the new core after replay and regression prove parity.
