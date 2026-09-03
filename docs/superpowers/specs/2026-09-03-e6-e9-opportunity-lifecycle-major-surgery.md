# E6-E9 Opportunity Lifecycle Major Surgery

## Objective

Make Production V2 preserve genuine developing opportunities across closed M5 candles while keeping trade authorization conservative. E6 remains the sole thesis owner; E7 may only confirm an E6 thesis; E8 remains the independent economic/risk gate; E9 remains final authority.

## Non-goals

- Do not lower score, RR, probability, or risk thresholds merely to increase trade count.
- Do not create a setup from a single indicator or from E7.
- Do not use an open candle or future candles.
- Do not bypass E8/E9 gates.
- Do not convert an unresolved opportunity into a trade-ready state merely because it persists.

## Lifecycle

A developing opportunity is distinct from a surviving trade thesis. The lifecycle may be:

`IDLE -> WAITING/WATCHING -> THESIS_FORMING -> THESIS_CONFIRMED -> READY -> EXECUTE`

or it may terminate as `INVALIDATED` when causal evidence is explicitly lost, direction changes, or thesis-specific invalidation occurs.

A pending opportunity keeps a stable opportunity identity across closed candles. Each new evaluation must use the newly closed candle and must not borrow future evidence.

## E6 contract

E6 consumes E1-E5 and owns causal setup formation. It may return a watch/developing thesis when the evidence is meaningful but incomplete. Structural space is an economic constraint, not by itself an opportunity invalidation. Genuine upstream directional contradiction or explicit E3 invalidation remains a hard veto.

Required distinction:

- `NO_CAUSAL_OPPORTUNITY`: no opportunity exists to track.
- `DEVELOPING_THESIS` / opportunity watch: opportunity exists, proof is incomplete, wait for the next closed candle.
- `INVALIDATED`: prior opportunity is no longer causally valid.
- `THESIS_CONFIRMED`: E6 has a coherent surviving thesis; E7 can evaluate confirmation.

## E7 contract

E7 never creates a thesis. If E6 has no surviving setup, E7 must return `NO_SETUP` / `CONFIRMATION_NOT_APPLICABLE` and may not report `CONFIRMATION_PROVEN`.

If E6 has a developing thesis, E7 may report pending confirmation and the exact next required event. Only setup-specific closed-candle evidence may promote confirmation.

Explicit invalidation has priority over positive confirmation evidence.

## E8 contract

E8 evaluates execution economics only after a surviving E6 thesis exists. Insufficient historical calibration remains visible and must not be hidden. Structural space, RR, probability/edge, execution uncertainty, and expectancy remain independent gates.

## E9 contract

E9 consumes the complete evidence chain and is the only trade-decision authority. `NO_TRADE` is mandatory whenever E6 thesis, E7 confirmation, or E8 economics is unresolved/failed.

## Persistence and duplicate candles

The lifecycle state and opportunity identity must survive across closed candles. Reprocessing the same candle must be skipped. A waiting opportunity must be evaluated exactly once on the next newly closed candle.

## Verification matrix

1. New developing opportunity -> WAITING/WATCHING with stable identity.
2. Existing WATCHING opportunity + valid upstream evidence -> remains WATCHING.
3. Developing opportunity + next closed candle -> progresses only on new evidence.
4. E6 no thesis -> E7 cannot confirm.
5. E6 thesis + E7 pending -> no trade.
6. E6 thesis + E7 confirmation + E8 fail/unresolved -> no trade.
7. E6 thesis + E7 confirmation + E8 pass -> E9 may authorize.
8. Direction change or explicit invalidation -> INVALIDATED.
9. Structural-space insufficiency -> wait/economic constraint, not automatic opportunity deletion.
10. Duplicate candle -> no second evaluation.
11. Closed-candle-only invariant remains true.
12. Existing E1 contract failures are corrected without weakening its market-state semantics.
