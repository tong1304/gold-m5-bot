# 3D Structural Failure

## 1. INPUT
- Recent structure event, subsequent closed candles and relevant structural levels.

## 2. PROCESSING
- Detect failure of a previously classified structural event through invalidation or failed continuation.

## 3. OUTPUT
- Failure state, failed event reference, evidence and confidence.

## 4. GATE
- FAIL when the prior event cannot be verified.
- Failure evidence does not itself mean reversal.

## 5. SCORE
- 0-100 failure-quality score based on confirmation and invalidation clarity.

## 6. TRACEABILITY
- Record original event ID, invalidation rule, candle timestamp, state and reason codes.