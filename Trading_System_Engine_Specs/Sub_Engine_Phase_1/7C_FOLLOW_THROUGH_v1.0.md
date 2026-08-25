# 7C Follow-through

## 1. INPUT
- Trigger event and immediately subsequent closed-candle behavior available at evaluation time.

## 2. PROCESSING
- Measure confirmation/follow-through after the trigger without looking beyond the allowed evaluation horizon.

## 3. OUTPUT
- Follow-through state, evidence, quality and confidence.

## 4. GATE
- FAIL when the required confirmation window is unavailable or data is invalid.

## 5. SCORE
- 0-100 follow-through score based on persistence and adverse behavior.

## 6. TRACEABILITY
- Record trigger ID, confirmation candles, evaluation timestamp, score and reason codes.