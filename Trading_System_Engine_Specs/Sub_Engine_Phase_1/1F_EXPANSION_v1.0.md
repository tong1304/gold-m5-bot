# 1F Expansion

## 1. INPUT
- Closed OHLC candles, true range/ATR and historical volatility baseline.

## 2. PROCESSING
- Detect expansion in realized range/volatility and distinguish sustained expansion from isolated noise.

## 3. OUTPUT
- Expansion state, magnitude evidence, persistence and confidence.

## 4. GATE
- FAIL only when required volatility observations are unavailable or invalid.
- Does not decide trade direction.

## 5. SCORE
- 0-100 expansion-quality score from magnitude, persistence and data stability.

## 6. TRACEABILITY
- Record measurement method, baseline, timestamp, state, score and reason codes.