# 6D Setup Invalidation

## 1. INPUT
- Setup definition/state, invalidation levels and subsequent closed candles.

## 2. PROCESSING
- Determine whether the setup remains structurally valid or has crossed its defined invalidation condition.

## 3. OUTPUT
- VALID/INVALID state, invalidation reason, triggering evidence and confidence.

## 4. GATE
- FAIL when an invalidation reference is undefined or unverifiable.
- An invalid setup cannot be resurrected by score.

## 5. SCORE
- Optional 0-100 invalidation-evidence quality score.

## 6. TRACEABILITY
- Record setup ID, invalidation rule, level, triggering candle and reason codes.