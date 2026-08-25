# 2C Mean-Reversion Behavior

## 1. INPUT
- Closed price, value/mean references permitted by the parent engine, volatility and range evidence.

## 2. PROCESSING
- Detect repeated movement away from and return toward an established mean without predicting the next move.

## 3. OUTPUT
- Mean-reversion behavior state, evidence, quality and confidence.

## 4. GATE
- FAIL when mean reference or supporting data is invalid.
- No entry decision.

## 5. SCORE
- 0-100 behavior-quality score based on repeatability, deviation and return evidence.

## 6. TRACEABILITY
- Record mean method, lookback, inputs, state, score and reason codes.