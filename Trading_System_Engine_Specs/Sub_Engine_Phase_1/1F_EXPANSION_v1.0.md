# 1F — EXPANSION

## 1. INPUT
Validated OHLCV and volatility/range history.

## 2. PROCESSING
Detect abnormal expansion of range/volatility relative to baseline and characterize persistence.

## 3. OUTPUT
Expansion state, magnitude/evidence, quality/confidence, reason codes.

## 4. GATE
BLOCK when baseline or current data is unreliable.

## 5. SCORE
Expansion quality 0–100; evidence only.

## 6. TRACEABILITY
Record measurements, baseline, source candles, state, score, gate, timestamp.

**DECISION BOUNDARY:** expansion classification only.