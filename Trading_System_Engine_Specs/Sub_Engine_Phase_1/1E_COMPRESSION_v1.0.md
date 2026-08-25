# 1E — COMPRESSION

## 1. INPUT
Validated OHLCV and volatility/range history from permitted inputs.

## 2. PROCESSING
Detect contraction of realized range/volatility relative to its baseline; do not predict breakout direction.

## 3. OUTPUT
Compression state, intensity/evidence, quality/confidence, reason codes.

## 4. GATE
BLOCK when the required historical baseline is unavailable or invalid.

## 5. SCORE
Compression quality 0–100; evidence only.

## 6. TRACEABILITY
Record baseline, lookback, measurements, state, score, gate, timestamp.

**DECISION BOUNDARY:** compression classification only.