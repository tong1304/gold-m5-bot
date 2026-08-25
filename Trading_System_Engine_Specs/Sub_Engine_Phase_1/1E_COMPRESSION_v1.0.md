# 1E Compression

## 1. INPUT
- Closed OHLC candles and volatility/range measurements from the allowed history.

## 2. PROCESSING
- Detect contraction of realized range/volatility relative to its own baseline.
- Classify COMPRESSION, NOT_COMPRESSION or UNCERTAIN.

## 3. OUTPUT
- Compression state, contraction evidence, intensity and confidence.

## 4. GATE
- FAIL only for invalid or insufficient volatility data.
- Compression is context evidence, not a breakout signal.

## 5. SCORE
- 0-100 compression-quality score based on persistence, magnitude and consistency.

## 6. TRACEABILITY
- Record baseline method, lookback, current measurements, state, score and reason codes.