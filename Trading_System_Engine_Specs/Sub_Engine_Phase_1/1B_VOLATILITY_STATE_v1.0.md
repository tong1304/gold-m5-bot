# 1B — VOLATILITY STATE

## 1. INPUT
Validated OHLCV and permitted volatility measures such as ATR/range statistics.

## 2. PROCESSING
Classify current volatility level and direction relative to its historical baseline without forecasting.

## 3. OUTPUT
Volatility state, evidence, quality/confidence, reason codes.

## 4. GATE
BLOCK only when required volatility inputs are invalid or insufficient.

## 5. SCORE
State quality 0–100; evidence only and never a trade authorization.

## 6. TRACEABILITY
Record source candles, lookback/version, measurements, state, score, gate, timestamp, reason codes.

**DECISION BOUNDARY:** volatility classification only.