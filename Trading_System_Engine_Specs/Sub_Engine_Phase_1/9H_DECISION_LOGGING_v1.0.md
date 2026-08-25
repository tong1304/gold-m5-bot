# 9H — DECISION LOGGING

## 1. INPUT
Final decision state and complete upstream trace/evidence metadata.

## 2. PROCESSING
Persist an immutable, replayable decision record without changing any decision.

## 3. OUTPUT
Structured decision log record, audit ID, schema/version metadata.

## 4. GATE
BLOCK logging only when mandatory audit fields are missing; this must not mutate the trading decision.

## 5. SCORE
No decision score. Logging completeness may be measured 0–100 for observability only.

## 6. TRACEABILITY
Record decision ID, symbol, timeframe, candle-close time, all engine/sub-engine versions, inputs/outputs, gates, scores, confidence, reasons.

**DECISION BOUNDARY:** logging/audit only; never alters execution eligibility.