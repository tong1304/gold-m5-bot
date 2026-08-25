# 1D — RANGE STATE

## 1. INPUT
Validated OHLCV, recent structural highs/lows, permitted range statistics.

## 2. PROCESSING
Determine whether price is exhibiting bounded/ranging behavior and estimate range stability.

## 3. OUTPUT
Range state, bounds evidence, quality/confidence, reason codes.

## 4. GATE
BLOCK when range evidence is insufficient or structurally invalid.

## 5. SCORE
Range-quality score 0–100; evidence only.

## 6. TRACEABILITY
Record source candles, bounds, lookback/version, state, score, gate, timestamp.

**DECISION BOUNDARY:** range classification only.