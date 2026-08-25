# 1C Trend State

## 1. INPUT
- Closed price series, permitted moving averages, directional measures and structure evidence available upstream.

## 2. PROCESSING
- Evaluate directional slope, alignment and persistence.
- Classify UP, DOWN, NEUTRAL or WEAK/UNSTABLE trend state.

## 3. OUTPUT
- Trend state, directional evidence, strength/quality and confidence.

## 4. GATE
- FAIL only if required trend inputs are invalid or insufficient.
- Never emits an entry decision.

## 5. SCORE
- 0-100 trend-quality score from alignment, slope and persistence; score is informational to the parent engine.

## 6. TRACEABILITY
- Record indicators, lookback, candle timestamp, classification, score and reason codes.