# 1C — TREND STATE

## 1. INPUT
Validated price history and permitted trend measures.

## 2. PROCESSING
Classify directional persistence, slope, and trend strength at the defined timeframe; do not interpret trade direction.

## 3. OUTPUT
Trend state, direction-neutral strength evidence, confidence, reason codes.

## 4. GATE
BLOCK when history or inputs are insufficient for reliable classification.

## 5. SCORE
Trend-state quality 0–100; evidence only.

## 6. TRACEABILITY
Record candles, lookback, indicator/version, classification, score, gate, timestamp.

**DECISION BOUNDARY:** state classification; no BUY/SELL.