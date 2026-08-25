# 7D Failure / Invalidation

## 1. INPUT
- Trigger/setup definitions, invalidation levels and closed candles after the trigger.

## 2. PROCESSING
- Detect trigger failure or invalidation according to the locked setup contract.

## 3. OUTPUT
- Failure state, invalidation event, evidence and confidence.

## 4. GATE
- FAIL when a verified invalidation occurs; no score may reverse this state.

## 5. SCORE
- Optional 0-100 evidence-quality score for the failure classification.

## 6. TRACEABILITY
- Record trigger/setup IDs, invalidation rule, candle timestamp and reason codes.