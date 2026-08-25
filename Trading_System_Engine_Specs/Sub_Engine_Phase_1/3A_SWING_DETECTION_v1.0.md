# 3A — SWING DETECTION

## 1. INPUT
Validated OHLCV, E1–E2 context, permitted historical candles.

## 2. PROCESSING
Detect confirmed swing highs/lows using causal rules; no future-dependent confirmation beyond the defined closed-candle rule.

## 3. OUTPUT
Swing events, indices/prices, confirmation state, confidence, reasons.

## 4. GATE
BLOCK when insufficient history prevents reliable swing detection.

## 5. SCORE
Swing quality 0–100; evidence only.

## 6. TRACEABILITY
Record candle IDs, algorithm/version, lookback, timestamp, score, gate.

**DECISION BOUNDARY:** swing detection only.