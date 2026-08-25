# 4E Reclaim / Failed Break

## 1. INPUT
- Reference level, breakout/penetration event and subsequent closed candles.

## 2. PROCESSING
- Detect return across a previously broken level and classify the prior break as sustained or failed.

## 3. OUTPUT
- Reclaim/failure state, level reference, event sequence and confidence.

## 4. GATE
- FAIL when the original break or level cannot be verified.

## 5. SCORE
- 0-100 reclaim-quality score from event sequence, close confirmation and level quality.

## 6. TRACEABILITY
- Record original event, reclaim candle, level ID, timestamp, score and reason codes.