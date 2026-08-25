# 7F Confirmation Quality

## 1. INPUT
- Trigger, follow-through, failure/invalidation and execution-condition outputs.

## 2. PROCESSING
- Aggregate confirmation evidence while preserving each component and hard failure.

## 3. OUTPUT
- Confirmation-quality state, component scores, confidence and blocking flags.

## 4. GATE
- FAIL when any mandatory confirmation condition is invalidated.
- This module does not make the final trade decision.

## 5. SCORE
- 0-100 aggregate confirmation score; hard failures cannot be offset.

## 6. TRACEABILITY
- Record all component IDs/versions, timestamp, aggregation rules and reason codes.