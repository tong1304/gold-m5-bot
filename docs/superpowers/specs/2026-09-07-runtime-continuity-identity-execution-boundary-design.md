# Runtime Continuity, Event Identity, and Order Execution Boundary Design

## Goal
Make Production V2 prove that an opportunity can persist across closed M5 candles, distinguish causal events from opportunity identity, and stop at an explicit order-execution boundary without weakening E9.

## Non-negotiable constraints
- E9 remains the sole final trade authority.
- No score, threshold, RR, pattern-quality, trigger-quality, or E9 standard is lowered or changed.
- A lifecycle stage may advance by at most one stage per closed candle.
- `opportunity_id` identifies the opportunity thesis and remains stable while that opportunity survives.
- `origin_event_id` identifies the causal event that created the opportunity and remains immutable for that opportunity.
- `event_id` identifies the latest causal event/evidence attached to the surviving opportunity and may change without changing `opportunity_id`.
- A genuinely new causal opportunity creates a new `opportunity_id`.
- Terminal opportunities cannot silently resume from stale evidence.
- `ORDER_INTENT` means E9 authorized an order intent only; it is not broker submission or execution.

## Lifecycle
`WATCH -> CONFIRMED -> E6_THESIS -> E7_CONFIRMED -> E8_READY -> TRADE`

Terminal states:
`TOO_LATE`, `EXPIRED`, `INVALIDATED`, `REPLACED`.

`TRADE` is an authorization state. It produces `ORDER_INTENT` and waits for the execution adapter to report the next boundary state.

## Identity model
Each active direction stores:
- `symbol`
- `direction`
- `opportunity_id`
- `origin_event_id`
- `event_id`
- `last_progression_candle`
- `stage_history`
- current lifecycle stage/state
- execution boundary state

The origin is never rewritten by later E4 events. The current event can move forward while the opportunity remains the same.

## Execution boundary
The state machine is:
`NONE -> ORDER_INTENT -> ORDER_SUBMITTED -> BROKER_ACCEPTED -> POSITION_OPEN`.

Only E9 may create `ORDER_INTENT`. A later adapter/reporting layer may move an authorized intent through submission/acceptance/open states. Failures must be explicit and must not be represented as `POSITION_OPEN`.

## Auditability
Every closed-candle progression records the candle and current event, and telemetry must expose stable opportunity identity plus origin/current event IDs, lifecycle stage, wait state, terminal state, and execution state.

## Testing contract
Tests must prove:
1. The same opportunity ID survives multiple candles while event_id changes.
2. origin_event_id remains unchanged across those candles.
3. Stage progression is at most one stage per candle.
4. A terminal opportunity does not reopen on the same event.
5. A genuinely new event can create a fresh opportunity.
6. E9 trade authorization is required before ORDER_INTENT.
7. ORDER_INTENT is not treated as broker execution.
8. Existing E9 outputs and thresholds remain untouched.
