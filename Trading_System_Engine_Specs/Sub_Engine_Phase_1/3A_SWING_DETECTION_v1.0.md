# 3A Swing Detection

## 1. INPUT
- Closed OHLC candles and the structure lookback permitted by Engine 3.

## 2. PROCESSING
- Identify confirmed swing highs/lows using only completed candles and a defined confirmation rule.

## 3. OUTPUT
- Swing events, prices, timestamps, confirmation status and confidence.

## 4. GATE
- FAIL when the lookback is insufficient or swing confirmation is not possible.

## 5. SCORE
- 0-100 swing-quality score based on prominence, separation and confirmation.

## 6. TRACEABILITY
- Record swing rule/version, source candles, confirmation timestamp, output and reason codes.