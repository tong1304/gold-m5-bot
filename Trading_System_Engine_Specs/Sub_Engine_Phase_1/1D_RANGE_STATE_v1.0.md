# 1D Range State

## 1. INPUT
- Closed OHLC series, recent highs/lows and permitted volatility measures.

## 2. PROCESSING
- Detect bounded price behavior, repeated boundary interaction and lack of directional persistence.
- Classify RANGE, NON_RANGE or UNCERTAIN.

## 3. OUTPUT
- Range state, boundaries/evidence, stability and confidence.

## 4. GATE
- FAIL only when the lookback is insufficient or range measurements are invalid.
- No independent trade direction.

## 5. SCORE
- 0-100 range-quality score using boundary clarity, containment and repeatability.

## 6. TRACEABILITY
- Store lookback, detected boundaries, measurements, state, score and reason codes.